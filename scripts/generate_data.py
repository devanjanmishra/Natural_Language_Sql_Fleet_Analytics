"""Generate synthetic fleet telemetry -> CSVs in data/.

Produces a small, realistic warehouse:
  - dim_vehicle:      a mixed fleet (diesel / electric / hybrid) across regions
  - fact_telemetry:   daily readings with occasional fault codes
  - maintenance_log:  free-text notes (used by the optional semantic module)

No external data download required — fully reproducible with a fixed seed.
"""
import csv
import os
import random
from datetime import date, datetime, timedelta

random.seed(42)
OUT = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT, exist_ok=True)

MODELS = [("FH16", "diesel"), ("FM12", "diesel"),
          ("eActros", "electric"), ("eCanter", "electric"),
          ("Hybrid-X", "hybrid")]

# Messy free-entry variants of each model, as they'd appear from manual logging.
# Canonicalization maps these back to the clean MODELS values above.
MODEL_VARIANTS = {
    "FH16":     ["FH16", "fh-16", "FH 16", "Volvo FH16", "fh16 "],
    "FM12":     ["FM12", "fm-12", "FM 12", "Volvo FM12"],
    "eActros":  ["eActros", "e-actros", "E Actros", "Mercedes eActros"],
    "eCanter":  ["eCanter", "e-canter", "E Canter", "Fuso eCanter"],
    "Hybrid-X": ["Hybrid-X", "hybrid x", "HybridX", "hyb-x"],
}
REGIONS = ["North", "South", "East", "West", "Central"]
FAULTS = ["P0217", "P0128", "C1234", "B1318", "U0100"]
NOTES = [
    "Replaced coolant sensor after recurring overheating warnings.",
    "Battery state-of-charge dropping faster than expected on long routes.",
    "Routine oil change and brake-pad inspection, no issues found.",
    "Engine temperature spikes intermittently under heavy load.",
    "Firmware update applied to telematics control unit.",
    "Fuel injector cleaned; fuel efficiency restored to baseline.",
    "Regenerative braking underperforming on electric unit.",
    "Tyre wear uneven, alignment corrected.",
]

N_VEHICLES = 40
DAYS = 90


def gen_vehicles():
    rows = []
    for vid in range(1, N_VEHICLES + 1):
        model, fuel = random.choice(MODELS)
        rows.append({
            "vehicle_id": vid,
            "registration": f"KA{random.randint(10,99)}{random.choice('ABCDEF')}{random.randint(1000,9999)}",
            "model": model,
            "model_raw": random.choice(MODEL_VARIANTS[model]),  # messy, for canonicalization
            "fuel_type": fuel,
            "region": random.choice(REGIONS),
            "in_service_date": (date(2022, 1, 1) + timedelta(days=random.randint(0, 700))).isoformat(),
        })
    return rows


def gen_telemetry(vehicles):
    rows = []
    start = datetime(2025, 1, 1, 8, 0, 0)
    for v in vehicles:
        odo = random.randint(20000, 180000)
        for d in range(DAYS):
            ts = start + timedelta(days=d, minutes=random.randint(0, 600))
            odo += random.randint(50, 400)
            is_ev = v["fuel_type"] == "electric"
            rows.append({
                "vehicle_id": v["vehicle_id"],
                "reading_ts": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "odometer_km": odo,
                "speed_kmph": round(random.uniform(0, 95), 1),
                "engine_temp_c": round(random.uniform(70, 115), 1),
                "fuel_level_pct": round(random.uniform(5, 100), 1),
                "battery_soc_pct": round(random.uniform(10, 100), 1) if is_ev else "",
                "fault_code": random.choice(FAULTS) if random.random() < 0.04 else "",
            })
    return rows


def gen_maintenance(vehicles):
    rows = []
    log_id = 1
    for v in vehicles:
        for _ in range(random.randint(0, 3)):
            rows.append({
                "log_id": log_id,
                "vehicle_id": v["vehicle_id"],
                "log_date": (date(2025, 1, 1) + timedelta(days=random.randint(0, DAYS))).isoformat(),
                "technician": random.choice(["A. Rao", "S. Khan", "M. Iyer", "P. Singh"]),
                "note": random.choice(NOTES),
            })
            log_id += 1
    return rows


def write_csv(name, rows):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows):>6} rows -> {name}")


if __name__ == "__main__":
    vehicles = gen_vehicles()
    write_csv("dim_vehicle.csv", vehicles)
    write_csv("fact_telemetry.csv", gen_telemetry(vehicles))
    write_csv("maintenance_log.csv", gen_maintenance(vehicles))
    print("done.")
