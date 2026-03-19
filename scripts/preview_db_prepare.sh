#!/bin/zsh

set -euo pipefail

typeset -a compose_cmd
compose_cmd=(
  docker compose
  -f docker-compose.yml
  -f docker-compose.preview.yml
)

admin_user=""
for candidate in odssws aquaintel; do
  if [[ "$("${compose_cmd[@]}" exec -T db psql -U "$candidate" -d postgres -Aqt -c "SELECT rolsuper FROM pg_roles WHERE rolname = current_user" 2>/dev/null)" == "t" ]]; then
    admin_user="$candidate"
    break
  fi
done

if [[ -z "$admin_user" ]]; then
  echo "Unable to connect to the preview database as a superuser (tried: odssws, aquaintel)." >&2
  exit 1
fi

"${compose_cmd[@]}" exec -T db psql -U "$admin_user" -d postgres -c "
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'odssws') THEN
    CREATE ROLE odssws LOGIN PASSWORD 'odssws';
  END IF;
END
\$\$;
"

if ! "${compose_cmd[@]}" exec -T db psql -U "$admin_user" -d postgres -Aqt -c "SELECT 1 FROM pg_database WHERE datname = 'odssws'" | grep -q '^1$'; then
  "${compose_cmd[@]}" exec -T db psql -U "$admin_user" -d postgres -c "CREATE DATABASE odssws OWNER odssws;"
fi

"${compose_cmd[@]}" exec -T db psql -U "$admin_user" -d postgres -c "ALTER DATABASE odssws OWNER TO odssws;"
"${compose_cmd[@]}" exec -T db psql -U "$admin_user" -d odssws -c "CREATE EXTENSION IF NOT EXISTS postgis;"
