# Running Fleet Insight

Two ways to run: **fully containerized** (one stack) or **local dev**.
Ollama always runs natively on your host machine in both cases (it manages
local models and GPU directly), so install it first either way:

```bash
# Host machine, both workflows:
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text        # only needed for the optional semantic module
# Ollama serves on http://localhost:11434 by default
```

---

## Option A — Docker (one-command stack)

Brings up the FastAPI app + MySQL together. The app reaches Ollama on the host
via `host.docker.internal`.

```bash
# 1. Build and start app + database
docker compose up --build -d

# 2. Generate synthetic data and load it (run inside the app container)
docker compose exec app python scripts/generate_data.py
docker compose exec app python scripts/load_mysql.py

# 3. Try it
curl localhost:8000/health
curl -X POST localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Which vehicle model has the most fault events?"}'
```

To include the optional Milvus semantic-search service:

```bash
docker compose --profile semantic up --build -d
```

Stop everything:

```bash
docker compose down            # add -v to also wipe the MySQL volume
```

---

## Option B — Local development (no app container)

Run only MySQL in Docker (or point at any MySQL/MariaDB you have), and run the
app directly with hot reload.

```bash
# 1. Start just the database
docker compose up -d mysql
# (or use an existing MySQL / MariaDB and set the env vars in .env)

# 2. Install deps + prepare data
pip install -r requirements.txt
python scripts/generate_data.py
python scripts/load_mysql.py

# 3. Run the API with reload
cp .env.example .env            # edit if your DB differs
uvicorn app.main:app --reload
```

Interactive API docs: http://localhost:8000/docs
