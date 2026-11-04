#!/usr/bin/env bash
# Starts Airflow for this project inside the apache/airflow container.
#  1. creates an "airflow" database in the project's Postgres (next to the Iceberg catalog,
#     but in its own database so the two never touch)
#  2. sets the local login admin / admin (Airflow's simple auth manager, for local use only)
#  3. migrates the Airflow tables and runs scheduler + DAG processor + API server + triggerer
set -euo pipefail

python - <<'EOF'
import time
import psycopg2

for attempt in range(60):
    try:
        conn = psycopg2.connect(host="postgres", user="iceberg", password="iceberg", dbname="iceberg")
        break
    except psycopg2.OperationalError:
        time.sleep(2)
else:
    raise SystemExit("Postgres did not answer within 2 minutes")
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT 1 FROM pg_database WHERE datname = 'airflow'")
if cur.fetchone() is None:
    cur.execute("CREATE DATABASE airflow")
    print("created database airflow")
EOF

echo "{\"admin\": \"${PAVS_AIRFLOW_PASSWORD:-admin}\"}" > "${AIRFLOW_HOME}/simple_auth_manager_passwords.json.generated"

airflow db migrate
exec airflow standalone
