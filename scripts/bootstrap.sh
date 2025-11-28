#!/bin/bash
set -euo pipefail

DB_NAME="${DB_NAME:-absurd_test}"

step() {
    echo "==> $1..."
}

fail() {
    echo "ERROR: $1" >&2
    exit 1
}

step "Creating database '$DB_NAME'"
if psql postgres -c "CREATE DATABASE $DB_NAME;" 2>/dev/null; then
    echo "    Created."
else
    psql postgres -c "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" -t | grep -q 1 \
        || fail "Could not create database. Is PostgreSQL running?"
    echo "    Already exists."
fi

step "Applying Absurd schema"
psql "$DB_NAME" -f src/absurd_test/sql/absurd.sql \
    || fail "Failed to apply schema. Check that src/absurd_test/sql/absurd.sql exists."

step "Creating Absurd queue 'agent_tasks'"
psql "$DB_NAME" -c "SELECT absurd.create_queue('agent_tasks');" >/dev/null 2>&1 \
    || echo "    Queue already exists."

step "Running Alembic migrations"
uv run alembic upgrade head \
    || fail "Migrations failed. Check alembic output above."

echo ""
echo "Done!"
