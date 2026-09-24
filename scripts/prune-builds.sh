#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/prune-builds.sh [--dry-run | --apply] [--keep IMAGE]

Lists, or with --apply removes, superseded opencascade.js build leftovers:
  images     project images older than the kept image and outside its
             ancestry: superseded localhost/opencascade.js tags and untagged
             build layers
  containers stopped containers whose image is a project image
  temp dirs  /var/tmp/ocjs*, /var/tmp/rockett-trial*, /tmp/ocjs* with no
             content newer than the kept image

A project image carries LABEL org.opencontainers.image.source=
https://github.com/msegec/opencascade.js or has "/opencascade.js/" or
"OCCT_COMMIT_HASH_FULL" in its build history. Anything else is never touched.

Always kept: the kept image (--keep, else localhost/opencascade.js:latest,
else the newest localhost/opencascade.js tag) and its ancestors, the pinned
emsdk base from the Dockerfile, images of running containers, ancestors of
tags outside localhost/opencascade.js, images newer than the kept image,
dist/, ocjs-trial, rockett-trial, ocjs-fleet-*, and *.md or *.patch notes.
EOF
}

mode=dry-run
keep_ref=
while (($#)); do
  case $1 in
    --dry-run) mode=dry-run ;;
    --apply) mode=apply ;;
    --keep) keep_ref=${2:?--keep needs an image}; shift ;;
    -h | --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

root=$(cd "$(dirname "$0")/.." && pwd)
repo=localhost/opencascade.js
base_digest=$(sed -n 's/^FROM [^ ]*@\(sha256:[0-9a-f]\{64\}\) .*/\1/p' "$root/Dockerfile" | head -n1)
[[ -n $base_digest ]] || { echo "no pinned base digest in Dockerfile" >&2; exit 1; }

mapfile -t all_ids < <(podman images -aq --no-trunc | sort -u)
images=$(podman image inspect "${all_ids[@]}")
containers=$(podman ps -a --format json)

if [[ -z $keep_ref ]]; then
  if podman image exists "$repo:latest"; then
    keep_ref=$repo:latest
  else
    keep_ref=$(jq -r --arg r "$repo:" '[.[] | select(any(.RepoTags[]?; startswith($r)))] | sort_by(.Created) | last | .RepoTags[0] // empty' <<<"$images")
  fi
fi
[[ -n $keep_ref ]] || { echo "no $repo image to keep; refusing to prune" >&2; exit 1; }
keep_id=$(podman image inspect --format '{{.Id}}' "$keep_ref")

plan=$(printf '%s\n%s\n' "$images" "$containers" | jq -r -s \
  --arg keep "$keep_id" --arg base "$base_digest" --arg repo "$repo:" '
  .[0] as $imgs | .[1] as $ctrs
  | def ts: .Created | sub("\\.[0-9]+"; "") | fromdateiso8601;
  def project: (.Labels["org.opencontainers.image.source"] // "") == "https://github.com/msegec/opencascade.js"
    or any(.History[]?; (.created_by // "") | test("/opencascade\\.js/|OCCT_COMMIT_HASH_FULL"));
  ($imgs | map({key: .Id, value: .}) | from_entries) as $m
  | def up: ($m[.].Parent // "") | select(. != "" and $m[.] != null);
    def chain: [recurse(up)];
    ($m[$keep] | ts) as $keep_ts
  | ([$keep | chain[]]
      + [$ctrs[] | select(.State == "running") | .ImageID | select($m[.] != null) | chain[]]
      + [$imgs[] | select(any(.RepoTags[]?; startswith($repo) | not)) | .Id | chain[]]
      + [$imgs[] | select(ts >= $keep_ts) | .Id | chain[]]
      + [$imgs[] | select(.Digest == $base or any(.RepoDigests[]?; endswith("@" + $base))) | .Id]
    | map({key: ., value: true}) | from_entries) as $keep_set
  | ($imgs[] | select(project and ($keep_set[.Id] | not))
      | "image|\(.Id)|\(.Created)|\(.RepoTags | join(","))|\(if (.RepoTags | length) > 0 then "superseded tag" else "untagged layer" end)"),
    ($imgs[] | select(project and ts >= $keep_ts and .Id != $keep)
      | "skip-image|\(.Id)|\(.Created)|\(.RepoTags | join(","))|newer than kept image"),
    ($ctrs[] | select(.State != "running" and .State != "paused") | select($m[.ImageID] | . != null and project)
      | "container|\(.Id)|\(.Created | todate)|\(.Names | join(","))|\(.State) from \(.Image)")
')

declare -A unique
while IFS=$'\t' read -r id size; do
  unique[$id]=$size
done < <(podman system df -v | awk -F'  +' '/^Images space usage/ {on=1; next} /^Containers space usage/ {on=0} on && $3 ~ /^[0-9a-f]{12}$/ {print $3 "\t" $7}')

to_bytes() {
  awk -v s="$1" 'BEGIN {n = s + 0; u = s; sub(/^[0-9.]+/, "", u); m["B"]=1; m["kB"]=1e3; m["MB"]=1e6; m["GB"]=1e9; m["TB"]=1e12; printf "%.0f", n * (u in m ? m[u] : 1)}'
}

human() { numfmt --to=si --suffix=B "$1"; }

keep_created=$(podman image inspect --format '{{.Created.Unix}}' "$keep_id")
echo "mode: $mode"
echo "kept image: $keep_ref ${keep_id:0:12} created $(date -d "@$keep_created" '+%F %T %Z')"
echo "kept base: emsdk@$base_digest"
echo

image_ids=()
image_total=0
echo "== images to remove (unique size per podman system df)"
while IFS='|' read -r kind id created tags why; do
  [[ $kind == image ]] || continue
  size=${unique[${id:0:12}]:-0B}
  image_total=$((image_total + $(to_bytes "$size")))
  image_ids+=("$id")
  printf '%s  %-10s %s  %s  %s\n' "${id:0:12}" "$size" "${created:0:19}" "${tags:-<none>}" "$why"
done <<<"$plan"
echo "images: ${#image_ids[@]}, unique total $(human "$image_total")"
echo

echo "== project images left alone (newer than kept image)"
while IFS='|' read -r kind id created tags why; do
  [[ $kind == skip-image ]] || continue
  printf '%s  %s  %s  %s\n' "${id:0:12}" "${created:0:19}" "${tags:-<none>}" "$why"
done <<<"$plan"
echo

container_ids=()
echo "== stopped containers to remove"
while IFS='|' read -r kind id created names why; do
  [[ $kind == container ]] || continue
  container_ids+=("$id")
  printf '%s  %s  %s  %s\n' "${id:0:12}" "$created" "$names" "$why"
done <<<"$plan"
echo "containers: ${#container_ids[@]}"
echo

stale_dir() {
  local p=$1 name=${1##*/}
  [[ -O $p ]] || return 1
  [[ -f $p && ( $name == *.md || $name == *.patch ) ]] && return 1
  case $name in ocjs-trial | rockett-trial | ocjs-fleet-*) return 1 ;; esac
  [[ -z $(find "$p" -newermt "@$keep_created" -print -quit 2>/dev/null) ]]
}

dirs=()
dir_total=0
echo "== temp paths to remove (no content newer than kept image)"
for p in /var/tmp/ocjs* /var/tmp/rockett-trial* /tmp/ocjs*; do
  [[ -e $p ]] || continue
  stale_dir "$p" || continue
  bytes=$(du -sb "$p" | cut -f1)
  dir_total=$((dir_total + bytes))
  dirs+=("$p")
  printf '%-10s %s  %s\n' "$(human "$bytes")" "$(date -r "$p" '+%F %T')" "$p"
done
echo "paths: ${#dirs[@]}, total $(human "$dir_total")"
echo
echo "reclaimable: $(human $((image_total + dir_total)))"

[[ $mode == apply ]] || { echo "dry run: nothing removed. Re-run with --apply to remove."; exit 0; }

failed=0
for id in "${container_ids[@]}"; do
  podman rm "$id" >/dev/null || failed=1
done
while read -r id; do
  [[ -n $id ]] || continue
  podman image exists "$id" || continue
  podman rmi --no-prune "$id" >/dev/null || failed=1
done < <(for id in "${image_ids[@]}"; do podman image inspect --format '{{.Created.Unix}} {{.Id}}' "$id" 2>/dev/null; done | sort -rn | cut -d' ' -f2)
for p in "${dirs[@]}"; do
  if stale_dir "$p"; then
    rm -rf -- "$p" || failed=1
  else
    echo "kept $p: changed since the dry run"
  fi
done
if ((failed)); then
  echo "some removals failed; see errors above" >&2
  exit 1
fi
echo "applied."
