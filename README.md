# Production Flight Booking MCP Server on AWS

Enterprise-grade **Model Context Protocol (MCP)** server for real-time flight search, seat mapping, atomic reservation workflows, cancellation policies, and operational analytics.

Deployed on **AWS ECS Fargate** behind an Application Load Balancer with Streamable HTTP (`/mcp`), SSE, and comprehensive platform guardrails.

---

## 🚀 Live AWS Endpoint

- **Base URL**: `https://my-62557ba230744e00bfa6dee1bce8609e.ecs.us-east-1.on.aws`
- **MCP Endpoint**: `https://my-62557ba230744e00bfa6dee1bce8609e.ecs.us-east-1.on.aws/mcp`
- **Health Check**: `https://my-62557ba230744e00bfa6dee1bce8609e.ecs.us-east-1.on.aws/health`
- **Prometheus Metrics**: `https://my-62557ba230744e00bfa6dee1bce8609e.ecs.us-east-1.on.aws/metrics`

---

## 🛠️ MCP Primitives

### 1. Tools

| Tool Name | Scope Required | Description |
|-----------|----------------|-------------|
| `search_flights_tool` | `flight:read` | Search available flights by origin, destination, date, cabin, and price |
| `get_flight_details_tool` | `flight:read` | Comprehensive flight schedule, aircraft model, and airport weather |
| `check_seat_availability_tool` | `flight:read` | Real-time cabin seat map breakdown and available seat numbers |
| `create_booking_tool` | `flight:book` | Atomically books ticket, assigns seat, and prevents double-booking |
| `get_booking_tool` | `flight:read` | Retrieves confirmed booking, ticket details, and flight status |
| `cancel_booking_tool` | `flight:book` | Cancels reservation, restores seat inventory, and calculates refund |
| `modify_booking_seat_tool` | `flight:book` | Changes assigned seat to another available seat in the same cabin |
| `get_audit_trail_tool` | `flight:admin` | Retrieves compliance audit log with execution latencies & SLA status |
| `query_flight_database_tool` | `sql:readonly`| Safe read-only SQL queries with AST validation (blocks write queries) |

### 2. Resources

| Resource URI | Description |
|--------------|-------------|
| `flight://airports/{code}` | Real-time airport status, active runways, and flight traffic |
| `flight://policies/cancellation` | Refund rules, 24h cooling-off window, and baggage allowances |
| `flight://analytics/daily-summary` | Fleet booking totals, gross revenue, and flight load factors |

### 3. Prompts

| Prompt Name | Purpose |
|-------------|---------|
| `flight_itinerary_assistant` | System prompt guiding LLM through search, seat selection, and booking |
| `disruption_rebooking_advisor` | System prompt assisting agents in disruption re-routing and refunds |

---

## 🛡️ Security & Guardrails

- **Authentication**: Bearer token or `X-API-Key` header:
  - `flight-agent-key-secret`: Scopes `flight:read`, `flight:book` (Rate limit: 120 RPM)
  - `flight-admin-key-secret`: Scopes `flight:read`, `flight:book`, `flight:admin`, `sql:readonly` (Rate limit: 300 RPM)
  - `flight-viewer-key-secret`: Scope `flight:read` (Rate limit: 60 RPM)
- **Token Bucket Rate Limiting**: Per-actor rate limiting preventing runaway agent loops.
- **SQL AST Validator**: Strictly allows `SELECT` statements; blocks `DROP`, `DELETE`, `INSERT`, `UPDATE`, `PRAGMA`, and multi-statement injection.
- **Transactional Idempotency**: `create_booking_tool` accepts an `idempotency_key` ensuring safe retries without double charging or duplicate seat allocation.

---

## 🧠 Where Do We Use the LLM in this Architecture?

In the **Model Context Protocol (MCP)** specification, the **MCP Server is NOT the LLM itself**. 

- The **MCP Server** (running on AWS ECS) is the **Capability & Deterministic Data Provider**. It exposes tools, resources, database transactions, RBAC authentication, and rate limiting.
- The **LLM** is the **Client Orchestrator ("The Brain")**. It reasons, plans, converses in natural human language, translates intent into structured tool calls, and handles business exceptions.

```
                                 ┌─────────────────────────────────────────────────────────┐
                                 │                 USER (Human or Chatbot)                 │
                                 └────────────────────────────┬────────────────────────────┘
                                                              │ "Book an economy flight from JFK
                                                              │  to London on Sep 28 for Alice"
                                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                             PRODUCTION AI AGENT (agent.py)                               │
│                                                                                          │
│  ┌──────────────────────────┐     System Prompt + Tools      ┌─────────────────────────┐ │
│  │   LLM (Reasoning Core)   │ ◄────────────────────────────► │ Orchestrator / ReAct    │ │
│  │  (Claude / GPT-4o /      │                                │ - Tool Calling Loop     │ │
│  │   Gemini / Llama 3)      │ ─── Tool Calls (JSON) ───────► │ - Policy Enforcement    │ │
│  └──────────────────────────┘                                │ - HITL Safety Gate      │ │
│                                                              └────────────┬────────────┘ │
└───────────────────────────────────────────────────────────────────────────┼──────────────┘
                                                                            │ MCP JSON-RPC 2.0
                                                                            │ (Streamable HTTP / SSE)
                                                                            │ Auth: Bearer Token
                                                                            ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                   AWS ECS FARGATE: PRODUCTION FLIGHT MCP SERVER                          │
│                   (https://my-62557ba230744e00bfa6dee1bce8609e.ecs.us-east-1.on.aws)     │
│                                                                                          │
│  ┌───────────────────────────┐   ┌───────────────────────────┐   ┌────────────────────┐  │
│  │  Transport Security       │   │  Token Bucket Rate Limit  │   │  RBAC Auth Layer   │  │
│  │  (DNS Rebinding, Hosts)   │──►│  (60-300 RPM per Actor)   │──►│  (Scopes: read/    │  │
│  │                           │   │                           │   │   book/admin/sql)  │  │
│  └───────────────────────────┘   └───────────────────────────┘   └─────────┬──────────┘  │
│                                                                            │             │
│            ┌───────────────────────────────┬───────────────────────────────┼─────────┐   │
│            ▼                               ▼                               ▼         ▼   │
│   ┌───────────────────┐           ┌──────────────────┐            ┌─────────┐   ┌─────┐  │
│   │ Tools (9)         │           │ Resources (3)    │            │ Prompts │   │Audit│  │
│   │ - search_flights  │           │ - airport data   │            │ - itiner│   │Log  │  │
│   │ - check_seats     │           │ - cancel policy  │            │ - disrup│   │SLA  │  │
│   │ - create_booking  │           │ - analytics      │            └─────────┘   └─────┘  │
│   │ - cancel_booking  │           └──────────────────┘                                   │
│   │ - modify_seat     │                                                                  │
│   └────────┬──────────┘                                                                  │
│            ▼                                                                             │
│   ┌───────────────────────────────────────────────────┐                                  │
│   │ Atomic SQLite Engine (WAL Mode, ACID Transactions)│                                  │
│   └───────────────────────────────────────────────────┘                                  │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### The 3 Production LLM Integration Patterns

---

## 📂 Project Architecture & Folder Structure

This repository adheres to enterprise **Clean Architecture** and **Separation of Concerns** standards for Model Context Protocol systems:

```
mcp-aws/
│
├── app/                          # 🚀 PRODUCTION MCP SERVER (Runs on AWS ECS Fargate)
│   ├── __init__.py
│   ├── config.py                 # Pydantic Settings & environment variables
│   ├── db.py                     # SQLite engine, WAL mode, ACID transactions & seed data
│   ├── auth.py                   # HTTP Bearer / API-Key authentication middleware
│   ├── guardrails.py             # RBAC scopes, token-bucket rate limiting, SQL AST validator
│   ├── tools.py                  # Guarded MCP tool implementations (9 domain tools)
│   ├── resources.py              # MCP resource URIs & handlers (airports, policies, analytics)
│   ├── prompts.py                # MCP prompt templates for LLMs (itinerary, disruption)
│   ├── telemetry.py              # Health check (/health) & Prometheus metrics (/metrics)
│   └── server.py                 # Starlette / FastMCP streamable HTTP application
│
├── agent/                        # 🧠 AUTONOMOUS AI AGENT (Client / LLM Orchestrator)
│   ├── __init__.py               # Public API exports (ProductionFlightAgent, MCPClient, etc.)
│   ├── __main__.py               # Direct execution: `python3 -m agent` or `python3 agent`
│   ├── cli.py                    # Command-line interface & argument parser
│   ├── client.py                 # Low-level JSON-RPC 2.0 MCP HTTP client
│   ├── models.py                 # Strongly-typed Dataclasses (ToolDefinition, ToolCall, etc.)
│   ├── safety.py                 # Human-In-The-Loop (HITL) Gate & approval policies
│   ├── orchestrator.py           # Core ReAct reasoning-acting loop & context manager
│   └── providers/                # Strategy Pattern: Pluggable LLM Providers
│       ├── __init__.py           # Provider factory (`create_provider(...)`)
│       ├── base.py               # Abstract Base Class (`LLMProvider`)
│       ├── openai_provider.py    # OpenAI / Azure / OpenAI-compatible (Ollama, vLLM)
│       ├── anthropic_provider.py # Anthropic Claude 3.5 Sonnet
│       └── cognitive_engine.py   # Resilient deterministic engine (zero-key fallback)
│
├── tests/                        # 🧪 AUTOMATED TEST SUITE (Unit, Integration & E2E)
│   ├── __init__.py
│   ├── test_db.py                # Database transactions, constraints & idempotency
│   ├── test_guardrails.py        # RBAC scopes, token bucket, SQL AST validation
│   ├── test_tools.py             # Domain tools business logic
│   ├── test_server.py            # HTTP endpoints (/health, /metrics, /mcp auth)
│   ├── test_agent.py             # Agent reasoning, tool conversion & HITL gates
│   └── test_smoke.py             # Fast sanity check
│
├── scripts/                      # 🛠️ OPERATIONAL & DEMO SCRIPTS
│   ├── __init__.py
│   └── client_demo.py            # 8-step JSON-RPC automated test script
│
├── run_agent.py                  # CLI launcher: `python3 run_agent.py --auto-approve`
├── client_demo.py                # Convenience launcher for scripts/client_demo.py
├── Dockerfile                    # Multi-stage production container build (copies only `app/`)
├── requirements.txt              # Production Python dependencies
├── .env.example                  # Environment variable reference
└── README.md                     # Comprehensive architecture & operational guide
```

---

## 🏛️ Best Practice Guidelines for MCP Repositories

### 1. Clear Server vs. Client Boundary
- **`app/`** contains **only** the server-side code deployed to AWS ECS Fargate. The Docker container copies *only* `app/`, ensuring lightweight, minimal container images without test fixtures, developer scripts, or client dependencies.
- **`agent/`** is the autonomous consumer of the MCP server. It connects to the server exclusively over the standardized Model Context Protocol JSON-RPC specification.

### 2. Hexagonal Architecture & Dependency Inversion (SOLID)
- **Strategy Pattern for LLMs (`agent/providers/`)**: The agent does not depend on a specific LLM vendor. Switching between OpenAI, Claude, local Ollama, or deterministic cognitive fallback requires zero changes to the orchestrator.
- **Strong Typing (`agent/models.py`)**: All tool definitions, tool calls, and agent steps use typed Python dataclasses rather than raw untyped dictionaries.

### 3. Human-In-The-Loop (HITL) Safety Perimeter (`agent/safety.py`)
- Read operations (`search_flights`, `check_seats`) execute autonomously.
- Mutating or financial operations (`create_booking`, `cancel_booking`) require explicit policy approval or interactive operator confirmation before dispatching to AWS.

### 4. Zero Hardcoded APIs (Dynamic Schema Discovery)
- The agent discovers tools at runtime using `tools/list` and translates JSON Schemas dynamically into OpenAI or Anthropic tool formats. If a new tool is deployed to the MCP server, the agent supports it immediately.

---

## 🤖 Running the Production AI Agent

Run the autonomous agent directly against our live AWS deployment:

```bash
# Activate environment
source .venv/bin/activate

# 1. Run with built-in resilient cognitive engine (no paid API keys required):
python3 run_agent.py --auto-approve

# 2. Run with OpenAI GPT-4o:
export OPENAI_API_KEY="sk-..."
python3 run_agent.py --backend openai --model gpt-4o

# 3. Run with Anthropic Claude 3.5 Sonnet:
export ANTHROPIC_API_KEY="sk-ant-..."
python3 run_agent.py --backend anthropic --model claude-3-5-sonnet-20241022

# 4. Run interactive mode with Human-in-the-Loop Safety Gate:
python3 run_agent.py --prompt "Find an economy flight from JFK to LHR on 2026-09-28 and book for Sarah Connor."
```

---

## 🧪 Testing Locally

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Run all unit & integration tests (29 tests)
python -m unittest discover tests

# 3. Start local development server
uvicorn app.server:app --host 0.0.0.0 --port 8080 --reload
```

---

## 📡 Example MCP Request

```bash
curl -X POST https://my-62557ba230744e00bfa6dee1bce8609e.ecs.us-east-1.on.aws/mcp \
  -H "Authorization: Bearer flight-agent-key-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "search_flights_tool",
      "arguments": {
        "origin": "JFK",
        "destination": "LHR",
        "cabin_class": "ECONOMY"
      }
    }
  }'
```

