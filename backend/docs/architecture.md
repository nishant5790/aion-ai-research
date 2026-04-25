# System Architecture & Flow

This document details the internal architecture, component interaction, request lifecycle, and the new **streaming agent progress** design of the AI Research System.

---

## High-Level Architecture

The system is built as a modular, tiered architecture that cleanly separates the API interface, business orchestration, intelligent reasoning, and vector storage.

```mermaid
graph TD
    User(["👤 User / Client"])
    API["🌐 FastAPI Layer\n(src/api/server.py)"]
    Orch["🔀 Research Pipeline\n(src/pipeline/orchestrator.py)"]
    DB[("🗄️ Qdrant Vector DB\n(src/db/database.py)")]
    Agent["🤖 Research Agent\n(src/agent/core.py)"]
    MCP["🌍 External Trends MCP\n(fetch_trends tool)"]

    User -- "POST /query" --> API
    API -- "process_query()" --> Orch
    Orch -- "semantic search" --> DB

    DB -- "cache HIT → report" --> Orch
    Orch -- "cache HIT → status:found" --> API
    API -- "200 + report" --> User

    Orch -- "cache MISS → task_id" --> API
    API -- "202 + task_id\nasyncio.create_task()" --> User

    subgraph "🔄 Async Streaming Background Task"
        Orch -- "astream(query)" --> Agent
        Agent -- "stream_mode=updates" --> Agent
        Agent -- "fetch_trends()" --> MCP
        MCP -- "trend data" --> Agent
        Agent -- "step update chunk" --> Orch
        Orch -- "append to steps[]" --> Orch
        Orch -- "save_report()" --> DB
    end

    User -- "GET /status?task_id=..." --> API
    API -- "steps[], status" --> User
```

---

## Streaming Agent Progress Flow

When the cache misses, the `/query` endpoint fires a **non-blocking async task** that streams each LangGraph node completion back to an in-memory task record. Clients poll `/status` to see `steps[]` grow in real time.

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI /query
    participant Orch as ResearchPipeline
    participant Agent as ResearchAgent (LangGraph)
    participant MCP as Trends MCP
    participant DB as Qdrant

    C->>API: POST /query {"query": "ML research"}
    API->>Orch: process_query()
    Orch->>DB: semantic_search()
    DB-->>Orch: no match (cache miss)
    Orch-->>API: {status: "processing", task_id: "abc"}
    API-->>C: 200 {task_id: "abc"}

    Note over API,Agent: asyncio.create_task(run_task_streaming)

    loop LangGraph ReAct steps
        Agent->>Agent: LLM reasoning  [step: model]
        Orch-->>Orch: steps.append({step:"model",...})
        Agent->>MCP: fetch_trends(topic, source) [step: tools]
        MCP-->>Agent: trend JSON
        Orch-->>Orch: steps.append({step:"tools",...})
    end

    Agent-->>Orch: final report text
    Orch->>DB: save_report(query, report)
    Orch-->>Orch: status = "completed"

    loop Polling
        C->>API: GET /status?task_id=abc
        API-->>C: {status:"processing", steps:[...]}
    end

    C->>API: GET /status?task_id=abc
    API-->>C: {status:"completed", steps:[...], report:"..."}
```

---

## Component Interaction Map

```mermaid
classDiagram
    class FastAPI {
        +startup_event()
        +create_query(request) QueryResponse
        +get_status(task_id) TaskStatusResponse
        +get_all_reports() dict
        +cleanup_db() dict
        +health() HealthResponse
    }

    class ResearchPipeline {
        +db: VectorDBContext
        +agent: ResearchAgent
        -_tasks: dict
        +initialize()
        +process_query(query) dict
        +run_task(task_id, query)
        +run_task_streaming(task_id, query)
        +get_task_status(task_id) dict
        +get_all_reports() list
        +cleanup()
    }

    class ResearchAgent {
        -_executor: LangGraph CompiledGraph
        +is_ready bool
        +build()
        +invoke(query) str
        +astream(query) AsyncGenerator
    }

    class VectorDBContext {
        +init_db()
        +search_query(query) str
        +save_report(query, report)
        +get_reports() list
        +cleanup()
    }

    class TaskStatusResponse {
        +status: str
        +report: str
        +error: str
        +steps: list
    }

    FastAPI --> ResearchPipeline : delegates all logic
    ResearchPipeline --> ResearchAgent : invoke / astream
    ResearchPipeline --> VectorDBContext : cache lookup & save
    FastAPI ..> TaskStatusResponse : returns from /status
```

---

## Data Flow — Cache Hit vs Miss

```mermaid
flowchart LR
    Q["🔍 Incoming Query"] --> SEM["Semantic Search\n(Qdrant cosine ≥ 0.85)"]

    SEM -- "HIT" --> CACHED["📦 Return Cached Report\nstatus: found"]
    SEM -- "MISS" --> TASK["🆕 Create task_id\nstatus: processing"]

    TASK --> ASYNC["asyncio.create_task()\nrun_task_streaming()"]

    ASYNC --> STEP1["Agent Step 1\nLLM Reasoning\nstep: model"]
    STEP1 --> STEP2["Agent Step 2\nTool Call → MCP\nstep: tools"]
    STEP2 --> STEPN["Agent Step N\nFinal Report\nstep: model"]
    STEPN --> SAVE["💾 save_report()\nQdrant vectorised"]
    SAVE --> DONE["✅ status: completed\nreport: ..."]

    STEP1 --> STATUS["📊 GET /status\nsteps growing…"]
    STEP2 --> STATUS
    STEPN --> STATUS
    DONE --> STATUS
```

---

## Core Components

### 1. API Layer — `src/api/`

The application entry point using **FastAPI**.

- **`server.py`** — All route definitions. `/query` is `async def` so `asyncio.create_task()` can be called directly on the event loop without blocking.
- **`models.py`** — Pydantic request/response schemas, including the `TaskStatusResponse.steps` field added for streaming.

### 2. Research Pipeline — `src/pipeline/orchestrator.py`

The orchestration hub between the DB and the agent.

| Method | Purpose |
|---|---|
| `process_query()` | Cache lookup; returns report or new `task_id` |
| `run_task()` | Sync agent invocation (original, untouched) |
| `run_task_streaming()` | **Async** — iterates `agent.astream()`, appends each step to `task["steps"]` in real time |
| `get_task_status()` | Returns the live task dict (polled by `/status`) |

### 3. Research Agent — `src/agent/core.py`

A **LangGraph ReAct graph** backed by `gemini-2.5-flash`.

| Method | Mode | Description |
|---|---|---|
| `build()` | Lifecycle | Compiles the LangGraph agent once at startup |
| `invoke(query)` | Sync | Blocking full run — returns final report string |
| `astream(query)` | **Async generator** | Yields `{step, content, data}` after every LangGraph node |

`astream()` calls the executor with `stream_mode="updates"`, meaning a chunk is emitted after **each node** (LLM call, tool call, etc.) completes — not just token-by-token.

### 4. Vector Database — `src/db/database.py`

A **Qdrant**-backed RAG layer.

- **Embeddings**: `models/gemini-embedding-001` → 3072-dimensional vectors
- **Similarity**: Cosine distance, threshold 0.85
- **Collections**: Named `research_reports`

---

## Request Lifecycle (Detailed)

```mermaid
stateDiagram-v2
    [*] --> Received : POST /query

    Received --> CacheHit : cosine similarity ≥ 0.85
    Received --> CacheMiss : no similar query found

    CacheHit --> [*] : 200 {status: found, report: "..."}

    CacheMiss --> Pending : task_id created
    Pending --> Processing : asyncio.create_task() fires
    Processing --> Streaming : agent.astream() iterating

    state Streaming {
        [*] --> ModelStep : LLM reasoning
        ModelStep --> ToolStep : tool_call detected
        ToolStep --> ModelStep : observation fed back
        ModelStep --> [*] : finish_reason STOP
    }

    Streaming --> Completed : report saved to Qdrant
    Streaming --> Failed : exception caught

    Completed --> [*] : next GET /status → {status: completed}
    Failed --> [*] : next GET /status → {status: failed, error: "..."}
```

---

## Testing Strategy

| Layer | Files | Coverage |
|---|---|---|
| Unit | `tests/test_agent.py`, `tests/test_pipeline.py` | Agent build/invoke mocks, pipeline state machine |
| Integration — Streaming | `tests/test_streaming.py` | Direct `astream()` + full HTTP poll flow |
| Interactive | `tests/component_checks.ipynb` | Manual DB / Agent / Pipeline exploration |

```bash
# All unit tests
uv run pytest tests/

# Streaming integration (requires live server)
uv run python tests/test_streaming.py
```

See the [Tests Directory](../tests/) for full details.
