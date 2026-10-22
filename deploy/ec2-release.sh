#!/usr/bin/env bash
# Invoked over SSH with an archive made by git archive of the verified commit.
set -Eeuo pipefail

revision=${1:?commit SHA required}
archive=${2:?source archive required}
if [[ ! "$revision" =~ ^[0-9a-f]{40}$ ]] || [[ ! -f "$archive" ]]; then
  echo 'A full commit SHA and existing source archive are required.' >&2
  exit 2
fi
deploy_dir=${KLAVE_DEPLOY_DIR:-$HOME/klave-engine}
archive=$(realpath "$archive")
cd "$deploy_dir"
deploy_dir=$PWD
test -f .env.prod
test -f docker-compose.ec2.yml
exec 9>.release.lock
flock -n 9

previous_image=$(sudo docker inspect --format '{{.Image}}' klave-api-1)
previous_compose="$deploy_dir/docker-compose.ec2.yml"
backup_revision=unknown
if [[ -f .release-current ]]; then
  previous_revision=$(cat .release-current)
  if [[ "$previous_revision" =~ ^[0-9a-f]{40}$ ]]; then
    backup_revision=$previous_revision
  fi
  if [[ "$previous_revision" =~ ^[0-9a-f]{40}$ ]] && \
      [[ -f ".releases/$previous_revision/docker-compose.ec2.yml" ]]; then
    previous_compose="$deploy_dir/.releases/$previous_revision/docker-compose.ec2.yml"
  fi
fi
mkdir -p .releases
staging=$(mktemp -d "$deploy_dir/.releases/.candidate-$revision-XXXXXX")
compose_file="$staging/docker-compose.ec2.yml"
export KLAVE_API_IMAGE="klave-api:$revision"
export KLAVE_BACKUP_IMAGE="klave-backup:$revision"
export KLAVE_SOURCE_COMMIT="$revision"
api_stopped=0

dc() {
  # bash -s reads this script over SSH; attached containers must not consume it.
  sudo --preserve-env=KLAVE_API_IMAGE,KLAVE_BACKUP_IMAGE,KLAVE_SOURCE_COMMIT docker compose \
    -p klave -f "$compose_file" --env-file "$deploy_dir/.env.prod" "$@" < /dev/null
}

recover() {
  status=$?
  trap - EXIT
  if (( status != 0 )); then
    compose_file=$previous_compose
    if (( api_stopped )); then
      echo 'Release failed; restoring the previous API image.' >&2
      # The initial deployment used this fixed tag; later releases use SHA tags.
      sudo docker tag "$previous_image" klave-api:ec2
      export KLAVE_API_IMAGE="$previous_image"
      if ! dc up -d --no-deps --no-build --wait --wait-timeout 180 api; then
        echo 'Automatic API restart failed; operator intervention is required.' >&2
      fi
    fi
  fi
  exit "$status"
}
trap recover EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Reject every unsafe member before extraction. Never unpack over active source.
python3 - "$archive" "$staging" <<'PY'
import sys, tarfile
from pathlib import PurePosixPath
with tarfile.open(sys.argv[1], 'r:gz') as archive:
    members = archive.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
            raise SystemExit('Unsafe release archive')
    archive.extractall(sys.argv[2], members=members, filter='data')
PY
test -f "$compose_file"
dc config --quiet
# Build while the previous API is still serving traffic.
dc build api backup
api_stopped=1
dc stop -t 120 api
# No API writes during the pre-upgrade snapshot; failure restarts the old image.
KLAVE_SOURCE_COMMIT="$backup_revision" dc run --rm --no-deps backup once
dc up -d --no-deps --no-build --wait --wait-timeout 180 api backup
dc exec -T api curl -fsS http://127.0.0.1:8000/ready
# Keep the documented manual Compose defaults on the accepted version too.
sudo docker tag "$KLAVE_API_IMAGE" klave-api:ec2
sudo docker tag "$KLAVE_BACKUP_IMAGE" klave-backup:ec2
# Keep accepted source immutable. A failed/repeated attempt cannot overwrite it.
if [[ -e ".releases/$revision" ]]; then
  echo 'Accepted source for this revision already exists; refusing overwrite.' >&2
  exit 2
fi
mv "$staging" ".releases/$revision"
printf '%s\n' "$revision" > .release-current.next
mv .release-current.next .release-current
echo "API release ready: $revision"
