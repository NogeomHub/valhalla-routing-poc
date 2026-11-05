#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p work/out work/tiles
cleanup() {
  docker logs valhalla-poc > work/out/service-final.log 2>&1 || true
  docker rm -f valhalla-poc valhalla-build-poc >/dev/null 2>&1 || true
}
trap cleanup EXIT
python3 scripts/poc.py prepare
IMAGE='ghcr.io/valhalla/valhalla@sha256:18cb42988e03c70dc4bc4ca095a259ec4db5e5df928be65956fc1c64c280b47a'
export IMAGE
# Bound the image pull and keep a record of the exact local image config.
timeout 300 docker pull "$IMAGE" > work/out/image-pull.log 2>&1
docker image inspect "$IMAGE" > work/out/image-inspect.json
timeout 30 docker run --rm --network none --entrypoint /bin/bash "$IMAGE" -ec '
  for tool in valhalla_build_tiles valhalla_build_config valhalla_service; do command -v "$tool"; done
  valhalla_build_tiles --help
  valhalla_service --help
' > work/out/tools.log 2>&1
# No external admin/timezone/elevation downloads. This limits semantic coverage.
timeout 900 docker run --rm --name valhalla-build-poc --network none --memory 6g --cpus 2 \
  --user "$(id -u):$(id -g)" -v "$PWD/work:/work" -w /work \
  --entrypoint /bin/bash "$IMAGE" -ec '
    valhalla_build_config --mjolnir-tile-dir /work/tiles --mjolnir-tile-extract "" \
      --mjolnir-concurrency 2 --mjolnir-id-table-size 10000000 \
      --httpd-service-listen "tcp://*:8002" \
      --mjolnir-data-processing-use-admin-db false > /work/out/config.json
    valhalla_build_tiles -c /work/out/config.json /work/pilot.osm.pbf
  ' > work/out/build.log 2>&1
python3 scripts/poc.py built
# The service is reachable only through the runner loopback interface.
docker run -d --name valhalla-poc --network bridge --memory 3g --cpus 2 \
  --user "$(id -u):$(id -g)" -v "$PWD/work:/work" -w /work \
  -p 127.0.0.1:8002:8002 --entrypoint valhalla_service \
  "$IMAGE" /work/out/config.json 1 > work/out/container-id.txt
python3 scripts/poc.py probe
docker logs valhalla-poc > work/out/service.log 2>&1
python3 scripts/poc.py report
