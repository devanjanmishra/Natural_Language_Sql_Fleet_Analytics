"""Introspect the live MySQL schema and render it as compact prompt context.

Grounding the LLM in the real schema is the single biggest lever for
NL-to-SQL accuracy — it prevents hallucinated tables and columns.
"""
from . import db


def get_schema_context() -> str:
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() ORDER BY table_name")
        tables = [r[0] for r in cur.fetchall()]

        lines = []
        for tbl in tables:
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s "
                "ORDER BY ordinal_position", (tbl,))
            cols = [f"{name} {dtype}" for name, dtype in cur.fetchall()]
            lines.append(f"TABLE {tbl} (" + ", ".join(cols) + ")")
        return "\n".join(lines)
    finally:
        conn.close()
