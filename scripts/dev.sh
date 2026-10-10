#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
IMAGE=${HOOKDOCTOR_IMAGE:-hookdoctor-dev:ubuntu24.04-amd64}
command -v docker >/dev/null || { echo 'ENVIRONMENT: install/start Docker Desktop.' >&2; exit 3; }
docker info >/dev/null 2>&1 || { echo 'ENVIRONMENT: Docker daemon unavailable; start Docker Desktop and retry.' >&2; exit 3; }
if [[ ${1:-} == build ]]; then
    exec docker build --platform linux/amd64 -t "$IMAGE" "$ROOT"
fi
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo 'ENVIRONMENT: run bash scripts/dev.sh build first.' >&2; exit 3; }
if [[ $(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$IMAGE") != linux/amd64 ]]; then
    echo 'ENVIRONMENT: image must be linux/amd64; rebuild it.' >&2
    exit 3
fi
if [[ $# == 0 ]]; then set -- bash; fi
if [[ -t 0 && -t 1 ]]; then set -- -it "$IMAGE" "$@"; else set -- "$IMAGE" "$@"; fi
exec docker run --rm --init --platform linux/amd64 --network none \
    --user "$(id -u):$(id -g)" --env HOME=/tmp \
    --mount "type=bind,source=$ROOT,target=/workspace" --workdir /workspace \
    "$@"
