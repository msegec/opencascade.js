#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
version=$(jq -r .version package.json)
commit=$(git rev-parse HEAD)
image="localhost/opencascade.js:$version"
out=${1:?pass a private output directory}
mkdir -p "$out"
out=$(realpath "$out")

podman build --network=none --pull=never --target custom-build-image -t "$image" .

stage=$(mktemp -d /tmp/ocjs-rockett-candidate-XXXXXX)
trap 'rm -rf -- "$stage"' EXIT
sed "s/#define OCJS_COMMIT unknown/#define OCJS_COMMIT $commit/" builds/rockett-cad.yml > "$stage/rockett-cad.yml"
grep -q "#define OCJS_COMMIT $commit" "$stage/rockett-cad.yml"

podman run --rm --network=none --workdir /output -v "$stage:/output:Z" "$image" /output/rockett-cad.yml
cp "$stage"/opencascade.rockett.{js,wasm,d.ts} dist/
npm pack --ignore-scripts --silent --pack-destination "$out"
cp "$stage"/opencascade.rockett.{js,wasm,d.ts} "$out/"
{
  printf 'Version: %s\nSource commit: %s\n' "$version" "$commit"
  podman image inspect --format 'Build image: {{.Id}}' "$image"
  sed -n 's/^FROM \([^ ]*\) AS base-image$/Base image: \1/p' Dockerfile
  sed -n 's/^ENV OCCT_COMMIT_HASH_FULL=/OCCT commit: /p' Dockerfile
} > "$out/build-info.txt"
(cd "$out" && sha256sum -- *.tgz opencascade.rockett.* > SHA256SUMS)
