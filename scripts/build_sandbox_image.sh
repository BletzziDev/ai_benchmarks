#!/usr/bin/env bash
# Build the Docker sandbox image used by `--sandbox docker`.
#   scripts/build_sandbox_image.sh [tag]
# Behind a TLS-intercepting proxy, set AIBENCH_BUILD_CA=/path/to/ca-bundle.pem; it is passed as a
# BuildKit secret (not baked into the image) and the build uses the host network to reach the proxy.
set -euo pipefail
TAG="${1:-aibench-sandbox:0.1}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ARGS=(-t "$TAG" -f "$HERE/docker/sandbox.Dockerfile")
if [[ -n "${AIBENCH_BUILD_CA:-}" ]]; then
  ARGS+=(--secret "id=ca,src=$AIBENCH_BUILD_CA" --network host)
  for v in HTTPS_PROXY HTTP_PROXY NO_PROXY https_proxy http_proxy no_proxy; do
    [[ -n "${!v:-}" ]] && ARGS+=(--build-arg "$v=${!v}")
  done
fi
DOCKER_BUILDKIT=1 docker build "${ARGS[@]}" "$HERE/docker"
echo "built $TAG"
