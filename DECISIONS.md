# Architecture Decisions

## API Pattern: Submit → Poll (not webhooks, SSE, or long-polling)

**Decision**: Async jobs with polling (`POST /jobs` → `GET /jobs/{id}` → `GET /jobs/{id}/result`).

**Why**: AI agents are the primary consumer. Polling is trivially implementable by any agent in 3 lines of code with no special infrastructure (no webhook receiver, no SSE parser, no persistent connection). Webhooks require agents to expose an HTTP endpoint, which most LLM-based agents cannot. Long-polling ties up server threads. Polling every 5–10 seconds is fine for a 10–60s pipeline.

---

## Database: SQLite + aiosqlite (not Postgres)

**Decision**: SQLite with WAL mode, accessed via `aiosqlite`.

**Why**: Zero infrastructure — no separate DB service, no connection string to manage on Railway. WAL mode gives adequate concurrent read performance for this workload. A single-server transcription API with < 100 concurrent users doesn't need Postgres. Easy to swap later if needed.

---

## Framework: FastAPI (not Flask)

**Decision**: FastAPI with async handlers.

**Why**: FastAPI auto-generates OpenAPI 3.1 from type annotations — critical for agent discoverability. Async support means background tasks (transcription) run without blocking the event loop. Pydantic schemas used in the existing codebase (`schemas.py`) integrate directly.

---

## Deployment: Railway (not GCP Cloud Run, Render, or Fly.io)

**Decision**: Railway with Dockerfile.

**Why**: Needs ffmpeg + PyTorch/Whisper (~2GB). Railway supports arbitrary Dockerfiles with persistent volumes (for SQLite), has a simple one-command deploy (`railway up`), and doesn't require pre-configuring GCP service accounts as deployment identities. Cloud Run would work but adds complexity (Cloud SQL or Firestore for state, GCS for file storage). Render works but has slower cold starts. Railway's free tier is sufficient for an assessment.

---

## Agent Discoverability: Three-layer approach

**Decision**: OpenAPI at `/openapi.json` + `llms.txt` at `/llms.txt` + MCP server.

**Why**:
- **OpenAPI**: Industry standard, consumed by LLM tool-use systems, Cursor, Copilot, etc.
- **llms.txt**: Emerging standard (llmstxt.org) — plain text instructions LLMs can read without parsing JSON. Provides step-by-step agent instructions at a well-known URL.
- **MCP (Model Context Protocol)**: Anthropic's standard for exposing tools to Claude. Lets Claude Desktop users invoke transcription directly from a conversation with zero API calls.
- **`/.well-known/ai-plugin.json`**: ChatGPT plugin format — widely indexed by agent frameworks.

---

## Error Design: Machine-readable + agent-actionable

**Decision**: Every error includes `code`, `retryable`, `retry_after_seconds`, and `suggested_action`.

**Why**: Agents can't read prose. A `retryable: true` flag tells an agent to retry without needing to parse the message. `suggested_action` gives the next concrete step. `retry_after_seconds` lets agents implement correct backoff without guessing.

---

## Pricing: $0.05/audio-minute after 60-minute free tier

**Decision**: Per-minute pricing after a free quota.

**Why**: Our pipeline costs $0.02–0.08/video. Competitors: AssemblyAI ($0.006/min), Deepgram ($0.0043/min), Google STT ($0.016/min). We're more expensive because we run a 3-stage pipeline (Whisper + Chirp 3 + Gemini), but output quality is higher (structured schema, speaker labels, translation). $0.05/min is a ~3× markup on average cost for sustainability.

---

## Auth: API keys via `X-API-Key` header (not OAuth, not JWT)

**Decision**: Static API keys in `X-API-Key` header.

**Why**: Simplest pattern for agent consumption. OAuth requires browser redirects (impossible for headless agents). JWTs add complexity with no benefit for a single-service API. Keys are hashed with SHA-256 before storage so a DB leak doesn't expose live keys. The `kf_live_` prefix helps secret scanners detect accidental commits.
