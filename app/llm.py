"""Ollama-backed NL-to-SQL with self-validation and result summarization.

Three LLM calls compose the pipeline:
  1. generate_sql   — natural-language question -> SQL, grounded in real schema
  2. validate_sql   — model reviews its own SQL for safety/validity (belt & braces)
  3. summarize      — query results -> plain-English answer for the stakeholder
"""
import json
import re
import requests
from . import config


def _chat(prompt: str, system: str = "") -> str:
    """Single-turn call to Ollama's /api/generate."""
    resp = requests.post(
        f"{config.OLLAMA_HOST}/api/generate",
        json={
            "model": config.OLLAMA_MODEL,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": 0.1},  # near-deterministic for SQL
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def _strip_sql_fence(text: str) -> str:
    """Pull SQL out of ```sql ... ``` fences if the model added them."""
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return (m.group(1) if m else text).strip().rstrip(";")


def generate_sql(question: str, schema_context: str) -> str:
    system = (
        "You are a senior analytics engineer. Translate the user's question "
        "into a single, valid MySQL SELECT query. Use ONLY the tables and "
        "columns in the provided schema. Never write INSERT/UPDATE/DELETE/DDL. "
        "Return ONLY the SQL — no commentary, no markdown."
    )
    prompt = f"SCHEMA:\n{schema_context}\n\nQUESTION:\n{question}\n\nSQL:"
    return _strip_sql_fence(_chat(prompt, system))


def validate_sql(sql: str, schema_context: str) -> dict:
    """Ask the model to sanity-check its own SQL. Returns {ok, reason, fixed_sql}."""
    system = (
        "You review MySQL queries. Respond ONLY with JSON: "
        '{"ok": bool, "reason": str, "fixed_sql": str}. '
        "Set ok=false if the query is not read-only, references unknown "
        "tables/columns, or is syntactically invalid. If you can fix it, put "
        "the corrected read-only query in fixed_sql; otherwise repeat the input."
    )
    prompt = f"SCHEMA:\n{schema_context}\n\nQUERY:\n{sql}\n\nReview:"
    raw = _chat(prompt, system)
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group(0)) if m else {}
        return {
            "ok": bool(data.get("ok", True)),
            "reason": data.get("reason", ""),
            "fixed_sql": _strip_sql_fence(data.get("fixed_sql", sql)) or sql,
        }
    except (json.JSONDecodeError, AttributeError):
        # If the validator misbehaves, fall back to the structural guard in db.py
        return {"ok": True, "reason": "validator-unparseable", "fixed_sql": sql}


def summarize(question: str, result: dict) -> str:
    system = (
        "You are a data analyst. Given a question and query results, write a "
        "concise, factual 1-3 sentence answer for a business stakeholder. "
        "Do not invent numbers beyond the data provided."
    )
    preview = {
        "columns": result.get("columns", []),
        "rows": result.get("rows", [])[:20],
        "row_count": result.get("row_count", 0),
    }
    prompt = (f"QUESTION:\n{question}\n\nRESULTS (JSON, truncated):\n"
              f"{json.dumps(preview, default=str)}\n\nAnswer:")
    return _chat(prompt, system)
