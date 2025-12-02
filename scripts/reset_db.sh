#!/bin/bash
set -euo pipefail

DB_NAME="${DB_NAME:-absurd_test}"

echo "==> Clearing all tasks and queue data from '$DB_NAME'..."
psql "$DB_NAME" <<SQL
TRUNCATE TABLE agent_jobs CASCADE;
TRUNCATE TABLE absurd.t_agent_tasks, absurd.r_agent_tasks, absurd.c_agent_tasks, absurd.e_agent_tasks, absurd.w_agent_tasks CASCADE;
SQL

echo "Done. All tasks cleared."
