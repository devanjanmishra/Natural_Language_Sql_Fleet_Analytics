"""Run SQL directly on the canonical CSV — no database server required.

DuckDB reads the CSV in place and runs full SQL over it, so you can query the
canonicalized data with proper GROUP BY / JOIN / window functions offline. This
is the "query the canonicalized data" path.

Usage:
  python scripts/query_canonical.py                      # run the built-in summary queries
  python scripts/query_canonical.py --sql "SELECT model, COUNT(*) FROM fleet GROUP BY model"
  python scripts/query_canonical.py --csv data/sample/fleet_canonical.csv
"""
import argparse
import duckdb

DEFAULT_CSV = "data/sample/fleet_canonical.csv"

# A few illustrative analytics queries over the cleaned columns.
SUMMARY_QUERIES = {
    "Fleet composition by canonical model": """
        SELECT model, COUNT(*) AS vehicles, SUM(fault_events) AS total_faults
        FROM fleet GROUP BY model ORDER BY vehicles DESC
    """,
    "Fault rate by fuel type": """
        SELECT fuel_type,
               COUNT(*) AS vehicles,
               SUM(fault_events) AS faults,
               ROUND(AVG(fault_events), 2) AS avg_faults_per_vehicle
        FROM fleet GROUP BY fuel_type ORDER BY avg_faults_per_vehicle DESC
    """,
    "Vehicles and avg odometer by region": """
        SELECT region, COUNT(*) AS vehicles, ROUND(AVG(odometer_km)) AS avg_odometer_km
        FROM fleet GROUP BY region ORDER BY vehicles DESC
    """,
    "Top 5 highest-fault vehicles": """
        SELECT vehicle_id, model, region, fault_events
        FROM fleet ORDER BY fault_events DESC LIMIT 5
    """,
}


def connect(csv_path: str):
    con = duckdb.connect()
    con.execute(f"CREATE VIEW fleet AS SELECT * FROM read_csv_auto('{csv_path}', header=true)")
    return con


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--sql", help="run a custom SQL query against view 'fleet'")
    args = ap.parse_args()

    con = connect(args.csv)

    if args.sql:
        print(con.execute(args.sql).fetchdf().to_string(index=False))
        return

    for title, q in SUMMARY_QUERIES.items():
        print(f"\n=== {title} ===")
        print(con.execute(q).fetchdf().to_string(index=False))


if __name__ == "__main__":
    main()
