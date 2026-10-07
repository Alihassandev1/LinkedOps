#!/usr/bin/env bash
set -euo pipefail
NEW_TAG="$1"
cd "$(dirname "$0")"

PREV="$(cat .current_tag 2>/dev/null || true)"
export IMAGE_TAG="$NEW_TAG"

docker compose pull web
docker compose up -d web

for i in $(seq 1 30); do
  status="$(docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q web)")"
  if [ "$status" = "healthy" ]; then
    echo "$NEW_TAG" > .current_tag
    echo "Deployed $NEW_TAG"
    exit 0
  fi
  sleep 2
done

echo "Deploy of $NEW_TAG failed; recent logs:"
docker compose logs --tail=50 web
if [ -n "$PREV" ]; then
  echo "Rolling back to $PREV"
  IMAGE_TAG="$PREV" docker compose up -d web
fi
exit 1