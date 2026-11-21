#!/usr/bin/env bash
# Runs the Django API and one paced worker for the web app to read.
#   scripts/backend.sh --fresh   new database, demo tenant, 20 seeded employees, all computed
#   scripts/backend.sh           reuse the database from last time
set -euo pipefail
cd "$(dirname "$0")/../.."
export PGPORT="${PGPORT:-5433}" PGDATABASE="${PGDATABASE:-backdate_demo}" LOG_LEVEL="${LOG_LEVEL:-WARNING}"
manage() { uv run python manage.py "$@"; }

if [[ "${1:-}" == "--fresh" ]]; then
  dropdb --if-exists "$PGDATABASE"
  createdb "$PGDATABASE"
  manage migrate -v0
  token=$(manage create_tenant demo)
  manage seed_payroll demo --employees 20
  manage backdate_worker --once
  cat > web/.env.local <<ENV
BACKDATE_API_URL=http://127.0.0.1:8000
BACKDATE_TOKEN=$token
BACKDATE_ALLOW_WRITES=true
ENV
  echo "wrote web/.env.local"
fi

trap 'kill 0' EXIT
manage runserver 127.0.0.1:8000 --noreload &
# --pace-ms slows each computation down a little, so leases are visible in the page.
manage backdate_worker --pace-ms 60 --idle-sleep 0.2 &
wait
