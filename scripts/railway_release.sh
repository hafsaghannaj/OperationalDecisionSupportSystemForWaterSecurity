#!/usr/bin/env bash
# Railway release command — runs before the new deployment goes live.
# Applies DB migrations and seeds multi-country demo data.
set -e

echo "==> Running Alembic migrations…"
alembic upgrade head

echo "==> Seeding multi-country demo data…"
python scripts/seed_multi_country.py

echo "==> Release complete."
