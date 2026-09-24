#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/upload-release-assets.sh TAG [--apply] [--image IMAGE]

Attaches the current build to an existing GitHub release of
msegec/opencascade.js. Dry run by default: packs and lists the assets,
uploads nothing.

Assets: the npm tarball (npm pack), every dist/opencascade.*.{js,wasm,d.ts},
build-info.txt (image id and digest, emsdk base digest, OCCT commit, git
commit) and SHA256SUMS. --apply uploads them with gh release upload
--clobber and appends the build info to the release notes once.

Refuses when the release does not exist (creating one is a publication and
is Mark's call), when TAG is not v<package.json version>, when HEAD is not
the tagged commit, when build inputs have uncommitted changes, or when a
dist artifact predates the build image.
IMAGE defaults to localhost/opencascade.js:<version>, then :latest.
EOF
}

gh_repo=msegec/opencascade.js
tag=
mode=dry-run
image=
while (($#)); do
  case $1 in
    --apply) mode=apply ;;
    --dry-run) mode=dry-run ;;
    --image) image=${2:?--image needs a reference}; shift ;;
    -h | --help) usage; exit 0 ;;
    -*) usage >&2; exit 2 ;;
    *) tag=$1 ;;
  esac
  shift
done
[[ -n $tag ]] || { usage >&2; exit 2; }

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
version=$(jq -r .version package.json)

fail() { echo "refusing: $*" >&2; exit 1; }

[[ $tag == "v$version" ]] || fail "tag $tag does not match package.json version $version (expected v$version)"
gh release view "$tag" -R "$gh_repo" --json tagName >/dev/null 2>&1 || fail "no release $tag on $gh_repo"
tag_commit=$(git rev-parse --verify --quiet "$tag^{commit}") || fail "tag $tag is not in the local clone; run git fetch --tags"
[[ $tag_commit == $(git rev-parse HEAD) ]] || fail "HEAD is not $tag; check out the tagged commit and rebuild"
[[ -z $(git status --porcelain -- Dockerfile src builds dist package.json .npmignore) ]] || fail "build inputs have uncommitted changes"

if [[ -z $image ]]; then
  for ref in "localhost/opencascade.js:$version" localhost/opencascade.js:latest; do
    podman image exists "$ref" && { image=$ref; break; }
  done
fi
[[ -n $image ]] || fail "no build image found; pass --image"

shopt -s nullglob
dist=(dist/opencascade.*.js dist/opencascade.*.wasm dist/opencascade.*.d.ts)
((${#dist[@]})) || fail "no dist/opencascade.* artifacts; build first"
image_created=$(podman image inspect --format '{{.Created.Unix}}' "$image")
for f in "${dist[@]}"; do
  (($(stat -c %Y "$f") >= image_created)) || fail "$f predates $image; rebuild dist from it"
done

stage=$(mktemp -d "${TMPDIR:-/tmp}/ocjs-release-XXXXXX")
trap 'rm -rf -- "$stage"' EXIT

npm pack --ignore-scripts --silent --pack-destination "$stage" >/dev/null
cp -- "${dist[@]}" "$stage/"

{
  echo "Build image: $image"
  podman image inspect --format 'Image id: {{.Id}}
Image digest: {{.Digest}}
Image created: {{.Created}}' "$image"
  echo "emsdk base: $(sed -n 's/^FROM \([^ ]*\) AS base-image$/\1/p' Dockerfile)"
  echo "OCCT commit: $(sed -n 's/^ENV OCCT_COMMIT_HASH_FULL=//p' Dockerfile)"
  echo "Git commit: $tag_commit"
} >"$stage/build-info.txt"

(cd "$stage" && sha256sum -- * >SHA256SUMS)

limit=$((2 * 1024 * 1024 * 1024))
echo "release: $gh_repo $tag"
echo "assets:"
for f in "$stage"/*; do
  size=$(stat -c %s "$f")
  ((size < limit)) || fail "${f##*/} is $size bytes; GitHub release assets must be under 2 GiB"
  printf '  %-12s %s\n' "$(numfmt --to=iec --suffix=B "$size")" "${f##*/}"
done
echo
cat "$stage/build-info.txt"
echo

if [[ $mode != apply ]]; then
  echo "dry run: nothing uploaded. Re-run with --apply to upload."
  exit 0
fi

gh release upload "$tag" "$stage"/* --clobber -R "$gh_repo"

notes=$(gh release view "$tag" -R "$gh_repo" --json body -q .body)
if ! grep -q '^Build image: ' <<<"$notes"; then
  printf '%s\n\n%s\n' "$notes" "$(cat "$stage/build-info.txt")" >"$stage/notes.md"
  gh release edit "$tag" -R "$gh_repo" --notes-file "$stage/notes.md" >/dev/null
fi
echo "uploaded to $(gh release view "$tag" -R "$gh_repo" --json url -q .url)"
