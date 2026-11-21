#!/usr/bin/env bash
# Everything CI runs, in one go, against the local Postgres.
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n== %s\n' "$1"; }

step "ruff";        uv run ruff check . && uv run ruff format --check .
step "mypy";        uv run mypy backdate server examples
step "bandit";      uv run bandit -q -r backdate server examples -x '*/migrations/*'
step "pip-audit";   uv export --frozen --no-dev --no-hashes --no-emit-project \
                      | uv run pip-audit -r /dev/stdin --strict
step "migrations";  uv run python manage.py makemigrations --check --dry-run
step "tests";       uv run pytest -q -p no:cacheprovider
printf '\nall checks passed\n'
