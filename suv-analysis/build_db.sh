#!/usr/bin/env bash
# build_db.sh — build the Turso database from the at-rest CSV, end to end.
#
# Turso (https://github.com/tursodatabase/turso) is the Rust rewrite of
# SQLite. Its shell binary is `tursodb`. This script is idempotent: it
# rebuilds suvs.db from data/suvs.csv every run.
#
# Why a shell script instead of one .sql file: Turso's `.import` is a shell
# meta-command, not SQL, so it must be fed on stdin — it is NOT honoured when
# a .sql file is supplied via redirection. We therefore stage the meta-command
# separately from the pure-SQL steps.
#
# Usage:  ./build_db.sh [DB_PATH]   (default DB_PATH=suvs.db)
set -euo pipefail

cd "$(dirname "$0")"
DB="${1:-suvs.db}"
CSV="data/suvs.csv"

command -v tursodb >/dev/null || {
    echo "error: 'tursodb' not found on PATH." >&2
    echo "Install Turso: https://github.com/tursodatabase/turso (or see README)." >&2
    exit 1
}
[ -f "$CSV" ] || { echo "error: $CSV not found" >&2; exit 1; }

echo ">> rebuilding $DB from $CSV"
rm -f "$DB" "$DB-wal" "$DB-shm"

# 1) staging table (all TEXT) so the CSV imports verbatim
tursodb -q "$DB" <<'SQL'
CREATE TABLE suvs_raw (
    model TEXT, year_start TEXT, year_end TEXT, generation TEXT,
    construction TEXT, weight_kg TEXT, wheel_track_mm TEXT, wheelbase_mm TEXT,
    length_mm TEXT, width_mm TEXT, height_mm TEXT, ground_clearance_mm TEXT,
    torsional_rigidity_rating TEXT, notes TEXT
);
SQL

# 2) import the CSV (meta-command on stdin; --skip 1 drops the header row)
printf '.import --csv --skip 1 %s suvs_raw\n' "$CSV" | tursodb -q "$DB"

# 3) typed table + cast, then drop staging
tursodb -q "$DB" <<'SQL'
CREATE TABLE suvs (
    model TEXT, year_start INTEGER, year_end INTEGER, generation TEXT,
    construction TEXT, weight_kg INTEGER, wheel_track_mm INTEGER,
    wheelbase_mm INTEGER, length_mm INTEGER, width_mm INTEGER,
    height_mm INTEGER, ground_clearance_mm INTEGER,
    torsional_rigidity_rating INTEGER, notes TEXT
);
INSERT INTO suvs SELECT
    model, CAST(year_start AS INTEGER), CAST(year_end AS INTEGER), generation,
    construction, CAST(weight_kg AS INTEGER), CAST(wheel_track_mm AS INTEGER),
    CAST(wheelbase_mm AS INTEGER), CAST(length_mm AS INTEGER),
    CAST(width_mm AS INTEGER), CAST(height_mm AS INTEGER),
    CAST(ground_clearance_mm AS INTEGER),
    CAST(torsional_rigidity_rating AS INTEGER), notes
FROM suvs_raw;
DROP TABLE suvs_raw;
SQL

# 4) the weighted off-road score, as a persistent view (mirrors analyze.py)
tursodb -q "$DB" < score_view.sql

ROWS=$(printf 'SELECT COUNT(*) FROM suvs;\n' | tursodb -q "$DB" -m list)
echo ">> done: $DB built with $ROWS vehicles, view 'suv_scores' ready"
echo ">> try:  tursodb $DB \"SELECT model, score FROM suv_scores ORDER BY score DESC LIMIT 10\""
