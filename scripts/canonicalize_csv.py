"""Canonicalize messy categorical columns in a CSV against target vocabularies.

Offline, file-based companion to the API's /canonicalize endpoints. Reads a raw
CSV, maps each configured column's values to a clean target set (anything that
doesn't fit -> "Other"), and writes a new CSV with canonical_<col> columns added.

Resolution order per value:
  1. Ollama LLM (semantic — knows "DSL"=Diesel, "EV"=Electric) if reachable
  2. Offline fallback: exact -> substring -> fuzzy (difflib) -> alias hints -> Other

The LLM path is the "real" one used in the service; the offline fallback makes
this script reproducible anywhere (CI, a laptop with no GPU) and is a deliberate
graceful-degradation pattern.

Usage:
  python scripts/canonicalize_csv.py \
      --in data/sample/fleet_raw.csv \
      --out data/sample/fleet_canonical.csv
  # force offline (skip Ollama):
  python scripts/canonicalize_csv.py --in ... --out ... --offline
"""
import argparse
import csv
import difflib
import json
import re

try:
    import requests  # only needed for the LLM path
except ImportError:
    requests = None

OTHER = "Other"
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5-coder:7b"

# Which columns to canonicalize, their target vocabulary, and the new column name.
COLUMN_CONFIG = {
    "model_raw": {
        "targets": ["FH16", "FM12", "eActros", "eCanter", "Hybrid-X"],
        "out": "model",
    },
    "fuel_raw": {
        "targets": ["Diesel", "Electric", "Hybrid"],
        "out": "fuel_type",
    },
    "region_raw": {
        "targets": ["North", "South", "East", "West", "Central"],
        "out": "region",
    },
}

# Optional hints for the OFFLINE fallback only (abbreviations the fuzzy matcher
# can't infer). The LLM does not need these.
ALIAS_HINTS = {
    "dsl": "Diesel", "ev": "Electric", "hyb": "Hybrid",
    "n": "North", "s": "South", "e": "East", "w": "West",
    "sth": "South", "ctrl": "Central", "cen": "Central",
}


# --------------------------------------------------------------------------
# offline fallback matcher
# --------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.strip().lower())


def fuzzy_map(value: str, targets: list[str]) -> str:
    v = _norm(value)
    norm_targets = {_norm(t): t for t in targets}

    if v in norm_targets:                       # exact (normalized)
        return norm_targets[v]
    for nt, t in norm_targets.items():          # substring either direction
        if nt and (nt in v or v in nt):
            return t
    close = difflib.get_close_matches(v, list(norm_targets), n=1, cutoff=0.72)
    if close:                                    # fuzzy
        return norm_targets[close[0]]
    if v in ALIAS_HINTS and ALIAS_HINTS[v] in targets:  # alias hint
        return ALIAS_HINTS[v]
    return OTHER


# --------------------------------------------------------------------------
# LLM path
# --------------------------------------------------------------------------
def ollama_available() -> bool:
    if requests is None:
        return False
    try:
        requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def llm_map(values: list[str], targets: list[str]) -> dict:
    system = (
        "You normalize messy categorical data. Map EACH raw value to the single "
        f'closest allowed target, or "{OTHER}" if none fits. Respond ONLY with a '
        "JSON object {raw: target}. Use only the allowed targets."
    )
    prompt = (f"ALLOWED TARGETS: {json.dumps(targets + [OTHER])}\n\n"
              f"RAW VALUES: {json.dumps(values)}\n\nJSON mapping:")
    resp = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "system": system,
              "stream": False, "options": {"temperature": 0.0}},
        timeout=120,
    )
    resp.raise_for_status()
    raw = resp.json().get("response", "")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    parsed = json.loads(m.group(0)) if m else {}
    # snap every value to a valid target; fall back to fuzzy if the model missed it
    lookup = {t.lower(): t for t in targets + [OTHER]}
    out = {}
    for val in values:
        proposed = str(parsed.get(val, "")).lower()
        out[val] = lookup.get(proposed) or fuzzy_map(val, targets)
    return out


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def build_mapping(values: list[str], targets: list[str], offline: bool) -> dict:
    if not offline and ollama_available():
        try:
            return llm_map(values, targets)
        except Exception as e:
            print(f"  [warn] LLM mapping failed ({e}); using offline fallback")
    return {v: fuzzy_map(v, targets) for v in values}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--out", dest="outfile", required=True)
    ap.add_argument("--offline", action="store_true", help="skip Ollama, use fuzzy fallback")
    args = ap.parse_args()

    with open(args.infile) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("input CSV is empty")

    mode = "offline fuzzy" if (args.offline or not ollama_available()) else "Ollama LLM"
    print(f"Canonicalizing {len(rows)} rows using: {mode}")

    mappings = {}
    for col, cfg in COLUMN_CONFIG.items():
        if col not in rows[0]:
            continue
        distinct = sorted({r[col] for r in rows if r[col] != ""})
        mapping = build_mapping(distinct, cfg["targets"], args.offline)
        mappings[col] = (cfg["out"], mapping)
        n_other = sum(1 for v in mapping.values() if v == OTHER)
        print(f"  {col:12} -> {cfg['out']:10} : {len(distinct)} variants, {n_other} -> Other")

    # write canonical CSV: original columns + canonical_<col> columns
    out_fields = list(rows[0].keys()) + [cfg[0] for cfg in mappings.values()]
    with open(args.outfile, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for r in rows:
            for col, (out_col, mapping) in mappings.items():
                r[out_col] = mapping.get(r[col], OTHER)
            w.writerow(r)
    print(f"wrote canonical CSV -> {args.outfile}")


if __name__ == "__main__":
    main()
