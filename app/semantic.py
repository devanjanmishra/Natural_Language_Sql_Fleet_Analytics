"""OPTIONAL: semantic search over free-text maintenance notes via Milvus.

This module is deliberately decoupled from the core NL-to-SQL path. It shows
vector-DB range: embed the maintenance_log notes with a local Ollama embedding
model, index them in Milvus, and answer fuzzy questions like
"which vehicles had cooling problems?" that keyword SQL handles poorly.

Enable with ENABLE_SEMANTIC=true and a running Milvus (see docker-compose.yml).
"""
import requests
from . import config, db

COLLECTION = "maintenance_notes"


def embed(text: str) -> list[float]:
    """Get an embedding vector from Ollama."""
    resp = requests.post(
        f"{config.OLLAMA_HOST}/api/embeddings",
        json={"model": config.EMBED_MODEL, "prompt": text},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def _client():
    from pymilvus import MilvusClient
    return MilvusClient(uri=f"http://{config.MILVUS_HOST}:{config.MILVUS_PORT}")


def build_index():
    """Read notes from MySQL, embed them, and (re)build the Milvus collection."""
    client = _client()
    conn = db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT log_id, vehicle_id, note FROM maintenance_log")
    notes = cur.fetchall()
    conn.close()

    if not notes:
        return {"indexed": 0}

    dim = len(embed(notes[0]["note"]))
    if client.has_collection(COLLECTION):
        client.drop_collection(COLLECTION)
    client.create_collection(collection_name=COLLECTION, dimension=dim)

    rows = [{
        "id": n["log_id"],
        "vector": embed(n["note"]),
        "vehicle_id": n["vehicle_id"],
        "note": n["note"],
    } for n in notes]
    client.insert(collection_name=COLLECTION, data=rows)
    return {"indexed": len(rows), "dim": dim}


def search(query: str, top_k: int = 5) -> list[dict]:
    client = _client()
    hits = client.search(
        collection_name=COLLECTION,
        data=[embed(query)],
        limit=top_k,
        output_fields=["vehicle_id", "note"],
    )
    return [{"vehicle_id": h["entity"]["vehicle_id"],
             "note": h["entity"]["note"],
             "distance": h["distance"]} for h in hits[0]]
