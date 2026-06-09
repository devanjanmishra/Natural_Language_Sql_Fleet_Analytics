"""Create the schema and load the generated CSVs into MySQL.

Usage:  python scripts/load_mysql.py
Assumes MySQL is running (see docker-compose.yml) and the env vars in
.env (or defaults in app/config.py) point at it.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import config  # noqa: E402
import mysql.connector  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
SCHEMA_SQL = os.path.join(os.path.dirname(__file__), "..", "sql", "schema.sql")


def connect(with_db=True):
    kw = dict(host=config.MYSQL_HOST, port=config.MYSQL_PORT,
              user=config.MYSQL_USER, password=config.MYSQL_PASSWORD)
    if with_db:
        kw["database"] = config.MYSQL_DB
    return mysql.connector.connect(**kw)


def ensure_db():
    conn = connect(with_db=False)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS {config.MYSQL_DB}")
    conn.commit()
    conn.close()


def run_schema():
    conn = connect()
    cur = conn.cursor()
    with open(SCHEMA_SQL) as f:
        for stmt in f.read().split(";"):
            if stmt.strip():
                cur.execute(stmt)
    conn.commit()
    conn.close()


def nullify(v):
    return None if v == "" else v


def load_table(name, columns):
    conn = connect()
    cur = conn.cursor()
    with open(os.path.join(DATA, f"{name}.csv")) as f:
        reader = csv.DictReader(f)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO {name} ({', '.join(columns)}) VALUES ({placeholders})"
        batch = [tuple(nullify(row[c]) for c in columns) for row in reader]
    cur.executemany(sql, batch)
    conn.commit()
    print(f"loaded {cur.rowcount:>6} rows -> {name}")
    conn.close()


if __name__ == "__main__":
    ensure_db()
    run_schema()
    load_table("dim_vehicle",
               ["vehicle_id", "registration", "model", "model_raw", "fuel_type", "region", "in_service_date"])
    load_table("fact_telemetry",
               ["vehicle_id", "reading_ts", "odometer_km", "speed_kmph",
                "engine_temp_c", "fuel_level_pct", "battery_soc_pct", "fault_code"])
    load_table("maintenance_log",
               ["log_id", "vehicle_id", "log_date", "technician", "note"])
    print("load complete.")
