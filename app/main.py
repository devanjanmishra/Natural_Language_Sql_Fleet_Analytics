"""FastAPI service: natural-language questions -> SQL -> answer.

Endpoints
  GET  /health          liveness + dependency check
  GET  /schema          the warehouse schema the LLM is grounded on
  POST /ask             {question} -> {sql, summary, columns, rows}
  POST /query           {sql}      -> raw read-only execution (power users)
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import db, llm, schema, config, canonicalize

app = FastAPI(
    title="Fleet Insight — AI-Augmented SQL Analytics",
    description="Ask fleet-telemetry questions in plain English; "
                "a local Ollama model writes, validates, and runs the SQL.",
    version="0.2.0",
)


class AskRequest(BaseModel):
    question: str


class QueryRequest(BaseModel):
    sql: str


class CanonProposeRequest(BaseModel):
    table: str
    column: str
    targets: list[str]


class CanonApplyRequest(BaseModel):
    table: str
    column: str
    mapping: dict


@app.get("/health")
def health():
    status = {"api": "ok"}
    try:
        db.run_query("SELECT 1 AS ok")
        status["mysql"] = "ok"
    except Exception as e:
        status["mysql"] = f"error: {e}"
    return status


@app.get("/schema")
def get_schema():
    try:
        return {"schema": schema.get_schema_context()}
    except Exception as e:
        raise HTTPException(500, f"Schema introspection failed: {e}")


@app.post("/ask")
def ask(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question must not be empty.")

    schema_ctx = schema.get_schema_context()

    # 1) generate
    sql = llm.generate_sql(req.question, schema_ctx)

    # 2) self-validate (LLM) then hard-gate (structural, authoritative)
    review = llm.validate_sql(sql, schema_ctx)
    sql = review["fixed_sql"]
    safe, reason = db.is_safe(sql)
    if not safe:
        raise HTTPException(400, f"Query rejected by safety gate: {reason}")

    # 3) execute
    try:
        result = db.run_query(sql)
    except Exception as e:
        raise HTTPException(400, f"Execution failed: {e}")

    # 4) summarize
    summary = llm.summarize(req.question, result)

    return {
        "question": req.question,
        "sql": sql,
        "validation": review["reason"],
        "summary": summary,
        "columns": result["columns"],
        "rows": result["rows"],
        "row_count": result["row_count"],
    }


@app.post("/query")
def query(req: QueryRequest):
    try:
        return db.run_query(req.sql)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/canonicalize/propose")
def canonicalize_propose(req: CanonProposeRequest):
    """Read-only: propose a mapping from a column's raw values to a target set."""
    if not req.targets:
        raise HTTPException(400, "Provide at least one target value.")
    try:
        return canonicalize.propose_mapping(req.table, req.column, req.targets)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Propose failed: {e}")


@app.post("/canonicalize/apply")
def canonicalize_apply(req: CanonApplyRequest):
    """Materialize a reviewed mapping as a non-destructive cleaned VIEW."""
    try:
        return canonicalize.apply_mapping(req.table, req.column, req.mapping)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Apply failed: {e}")
