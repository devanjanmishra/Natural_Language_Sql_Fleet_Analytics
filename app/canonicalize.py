"""Column value canonicalization: map messy raw values to a clean standard set.

Two stages, deliberately separated:
  1. propose_mapping  — read DISTINCT values from a column, ask the LLM to map
                        each to the nearest target value (or "Other"). Read-only.
  2. apply_mapping    — materialize the mapping as a CASE-based cleaned VIEW so
                        raw and canonical values sit side by side. Non-destructive.

The LLM maps to a CONTROLLED target vocabulary the caller supplies; anything it
can't confidently place falls back to "Other". This mirrors the pattern in the
standalone Canonicalization-via-Ollama-LLMs project, extended to operate
directly against a SQL warehouse.

Safety: the apply step is the only non-SELECT path in the service. It is NOT
reachable from the natural-language endpoint, and it allow-lists table/column
names against the live schema to prevent injection.
"""
import json
import re
import requests

from . import config, db

OTHER = "Other"


# --------------------------------------------------------------------------
# Stage 1 — propose
# --------------------------------------------------------------------------
def _distinct_values(table: str, column: str, limit: int = 200) -> list[str]:
    _assert_identifier(table)
    _assert_identifier(column)
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        # identifiers are validated against the schema in _assert_in_schema
        cur.execute(
            f"SELECT DISTINCT `{column}` FROM `{table}` "
            f"WHERE `{column}` IS NOT NULL LIMIT {int(limit)}"
        )
        return [str(r[0]) for r in cur.fetchall()]
    finally:
        conn.close()


def propose_mapping(table: str, column: str, targets: list[str]) -> dict:
    """Ask the LLM to map each distinct raw value to a target (or 'Other').

    Returns {"mapping": {raw: canonical}, "targets": [...], "unmapped": [...]}.
    """
    _assert_in_schema(table, column)
    raws = _distinct_values(table, column)
    if not raws:
        return {"mapping": {}, "targets": targets, "unmapped": []}

    target_set = list(dict.fromkeys(targets + [OTHER]))  # dedupe, keep order
    system = (
        "You normalize messy categorical data. Map EACH raw value to the single "
        "closest value in the allowed target list. If a raw value does not "
        f'clearly match any target, map it to "{OTHER}". '
        "Respond ONLY with a JSON object {raw_value: target_value}. "
        "Every raw value must appear exactly once. Use only targets from the list."
    )
    prompt = (
        f"ALLOWED TARGETS: {json.dumps(target_set)}\n\n"
        f"RAW VALUES: {json.dumps(raws)}\n\n"
        "JSON mapping:"
    )
    mapping = _coerce_mapping(_chat(prompt, system), raws, target_set)
    unmapped = sorted({k for k, v in mapping.items() if v == OTHER})
    return {"mapping": mapping, "targets": target_set, "unmapped": unmapped}


def _coerce_mapping(raw_response: str, raws: list[str], targets: list[str]) -> dict:
    """Parse the model's JSON and enforce: every raw present, every value a target."""
    try:
        m = re.search(r"\{.*\}", raw_response, re.DOTALL)
        parsed = json.loads(m.group(0)) if m else {}
    except (json.JSONDecodeError, AttributeError):
        parsed = {}

    target_lookup = {t.lower(): t for t in targets}
    clean = {}
    for r in raws:
        proposed = parsed.get(r, OTHER)
        # snap to a valid target (case-insensitive); else Other
        clean[r] = target_lookup.get(str(proposed).lower(), OTHER)
    return clean


# --------------------------------------------------------------------------
# Stage 2 — apply (non-destructive: build a cleaned VIEW)
# --------------------------------------------------------------------------
def apply_mapping(table: str, column: str, mapping: dict,
                  view_suffix: str = "_clean") -> dict:
    """Create/replace a VIEW exposing a canonical_<column> next to the original.

    Non-destructive: the source table is never modified. Re-runnable: CREATE OR
    REPLACE VIEW. Returns the view name and the SQL used.
    """
    _assert_in_schema(table, column)
    if not mapping:
        raise ValueError("Empty mapping; run propose_mapping first.")

    view = f"{table}{view_suffix}"
    _assert_identifier(view)

    # Build a CASE expression with fully parameter-escaped literals.
    whens = []
    for raw, canon in mapping.items():
        whens.append(f"WHEN `{column}` = {_q(raw)} THEN {_q(canon)}")
    case_expr = "CASE " + " ".join(whens) + f" ELSE {_q(OTHER)} END"

    ddl = (
        f"CREATE OR REPLACE VIEW `{view}` AS "
        f"SELECT t.*, {case_expr} AS `canonical_{column}` "
        f"FROM `{table}` t"
    )

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(ddl)
        conn.commit()
    finally:
        conn.close()

    return {"view": view, "canonical_column": f"canonical_{column}", "ddl": ddl}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _q(val: str) -> str:
    """Escape a string literal for safe inlining in DDL (single quotes doubled)."""
    return "'" + str(val).replace("\\", "\\\\").replace("'", "''") + "'"


def _assert_identifier(name: str):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or ""):
        raise ValueError(f"Illegal SQL identifier: {name!r}")


def _assert_in_schema(table: str, column: str):
    """Allow-list table+column against the live schema — blocks injection."""
    _assert_identifier(table)
    _assert_identifier(column)
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
            (table, column),
        )
        if cur.fetchone()[0] == 0:
            raise ValueError(f"Unknown table/column: {table}.{column}")
    finally:
        conn.close()


def _chat(prompt: str, system: str = "") -> str:
    resp = requests.post(
        f"{config.OLLAMA_HOST}/api/generate",
        json={
            "model": config.OLLAMA_MODEL,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": 0.0},  # deterministic mapping
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()
