"""MySQL access layer with a hard read-only guard."""
import mysql.connector
from mysql.connector import Error
from . import config


def get_connection():
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DB,
    )


def is_safe(sql: str) -> tuple[bool, str]:
    """Defense in depth: structurally reject anything that isn't a read.

    The LLM is also asked to self-validate, but we never trust that alone —
    this function is the authoritative gate before execution.
    """
    stripped = sql.strip().rstrip(";").lstrip()
    upper = stripped.upper()

    if not upper.startswith(config.ALLOWED_SQL_PREFIXES):
        return False, "Only SELECT / WITH (read-only) queries are permitted."

    # Block stacked statements (e.g. "SELECT 1; DROP TABLE x").
    if ";" in stripped:
        return False, "Multiple statements are not allowed."

    forbidden = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
                 "TRUNCATE", "CREATE", "GRANT", "REPLACE", "INTO OUTFILE")
    for kw in forbidden:
        # word-boundary-ish check to avoid matching column names
        if f" {kw} " in f" {upper} " or upper.startswith(kw):
            return False, f"Forbidden keyword detected: {kw}."

    return True, "ok"


def run_query(sql: str) -> dict:
    """Execute a validated read query and return columns + rows."""
    safe, reason = is_safe(sql)
    if not safe:
        raise ValueError(reason)

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql)
        rows = cur.fetchmany(config.MAX_ROWS)
        cols = [d[0] for d in cur.description] if cur.description else []
        return {"columns": cols, "rows": rows, "row_count": len(rows)}
    except Error as e:
        raise RuntimeError(f"MySQL error: {e}")
    finally:
        conn.close()
