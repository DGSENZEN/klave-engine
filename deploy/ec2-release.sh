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
cd "$deploy_dir"
test -f .env.prod
test -f docker-compose.ec2.yml
exec 9>.release.lock
flock -n 9

previous_image=$(sudo docker inspect --format '{{.Image}}' klave-api-1)
previous_compose=".release-compose-$revision.previous.yml"
cp docker-compose.ec2.yml "$previous_compose"
export KLAVE_API_IMAGE="klave-api:$revision"
export KLAVE_BACKUP_IMAGE="klave-backup:$revision"
api_stopped=0

dc() {
  sudo --preserve-env=KLAVE_API_IMAGE,KLAVE_BACKUP_IMAGE docker compose \
    -p klave -f docker-compose.ec2.yml --env-file .env.prod "$@"
}

recover() {
  status=$?
  trap - EXIT
  if (( status != 0 )); then
    cp "$previous_compose" docker-compose.ec2.yml
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

tar -xzf "$archive"
dc config --quiet
# Build while the previous API is still serving traffic.
dc build api backup
api_stopped=1
dc stop -t 120 api
# No API writes during the pre-upgrade snapshot; failure restarts the old image.
dc run --rm --no-deps backup once
dc up -d --no-deps --no-build --wait --wait-timeout 180 api backup
dc exec -T api curl -fsS http://127.0.0.1:8000/ready
# Keep the documented manual Compose defaults on the accepted version too.
sudo docker tag "$KLAVE_API_IMAGE" klave-api:ec2
sudo docker tag "$KLAVE_BACKUP_IMAGE" klave-backup:ec2
printf '%s\n' "$revision" > .release-current
echo "API release ready: $revision"
