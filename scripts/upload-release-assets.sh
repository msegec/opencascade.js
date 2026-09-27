#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/upload-release-assets.sh TAG CANDIDATE_DIR [--apply]

Attaches a build from scripts/build-rockett-candidate.sh CANDIDATE_DIR to an
existing GitHub release of msegec/opencascade.js. Dry run by default: stages
and lists the assets, uploads nothing.

Assets: every file the candidate's SHA256SUMS lists (npm tarball and kernel),
the candidate's build-time build-info.txt, and SHA256SUMS over all of them.
--apply uploads them with gh release upload --clobber and appends the build
info to the release notes once.

Refuses when the release does not exist (creating one is a publication and
is Mark's call), when TAG is not v<package.json version>, when HEAD is not
the tagged commit, when build inputs have uncommitted changes, when the
candidate has no build-info.txt or its Source commit is not the tagged
commit, or when a candidate file no longer matches its build-time hash.
EOF
}

gh_repo=msegec/opencascade.js
tag=
candidate=
mode=dry-run
while (($#)); do
  case $1 in
    --apply) mode=apply ;;
    --dry-run) mode=dry-run ;;
    -h | --help) usage; exit 0 ;;
    -*) usage >&2; exit 2 ;;
    *)
      if [[ -z $tag ]]; then tag=$1
      elif [[ -z $candidate ]]; then candidate=$1
      else usage >&2; exit 2
      fi ;;
  esac
  shift
done
[[ -n $tag && -n $candidate ]] || { usage >&2; exit 2; }
candidate=$(realpath -m -- "$candidate")

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
version=$(jq -r .version package.json)

fail() { echo "refusing: $*" >&2; exit 1; }

[[ $tag == "v$version" ]] || fail "tag $tag does not match package.json version $version (expected v$version)"
gh release view "$tag" -R "$gh_repo" --json tagName >/dev/null 2>&1 || fail "no release $tag on $gh_repo"
tag_commit=$(git rev-parse --verify --quiet "$tag^{commit}") || fail "tag $tag is not in the local clone; run git fetch --tags"
[[ $tag_commit == $(git rev-parse HEAD) ]] || fail "HEAD is not $tag; check out the tagged commit and rebuild"
[[ -z $(git status --porcelain -- Dockerfile src builds dist package.json .npmignore) ]] || fail "build inputs have uncommitted changes"

[[ -f $candidate/build-info.txt ]] || fail "$candidate/build-info.txt is missing; build with scripts/build-rockett-candidate.sh"
built_commit=$(sed -n 's/^Source commit: //p' "$candidate/build-info.txt")
[[ $built_commit == "$tag_commit" ]] || fail "candidate was built from '${built_commit:-unknown}', not $tag ($tag_commit)"
[[ -f $candidate/SHA256SUMS ]] || fail "$candidate/SHA256SUMS is missing"
(cd "$candidate" && sha256sum --check --strict --quiet SHA256SUMS) || fail "candidate files do not match their build-time SHA256SUMS"

stage=$(mktemp -d "${TMPDIR:-/tmp}/ocjs-release-XXXXXX")
trap 'rm -rf -- "$stage"' EXIT

while read -r _ name; do
  cp -- "$candidate/$name" "$stage/"
done <"$candidate/SHA256SUMS"
cp -- "$candidate/build-info.txt" "$stage/"

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
