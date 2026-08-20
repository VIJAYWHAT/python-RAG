# Ejadah HR AI Assistant — backend

RAG-based HR assistant for the Ejadah employee app. It answers two
kinds of question:

| Question | Answered from |
|---|---|
| "What is my leave balance?" | The employee's own record, read live from the Ejadah HR APIs |
| "What is the annual leave policy?" | The HR policy knowledge base (Chroma + embeddings) |

Routing between the two happens in `employee/employee_query_detector.py`.

---

## The one thing to understand first

**Every answer is scoped to the employee that the access token
belongs to, and that employee is never taken from the request.**

The Flutter app already holds an Ejadah `AccessToken` from
`userLogin`. It sends that token; the backend verifies it against
Ejadah's own API and reads the employee number out of the *response*.
There is no `employee_id` field on any request body — no field a
tampered client could set to read a colleague's salary.

Read `ejadah/identity_service.py` before changing anything in the auth
path. Its docstring sets out the three verification layers and, just
as importantly, the one residual risk and how to close it.

---

## Running it

### Local

```bash
python -m venv .venv
.venv/Scripts/activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill in GROQ_API_KEY
python run.py
```

Set `ENVIRONMENT=local` in `.env` while developing. `production`
refuses to start on an unsafe configuration (see
`Settings.validate_for_production`), which is what you want in a
deployment and not what you want on a laptop.

### Working offline

With no route to Ejadah staging, set both:

```
ENVIRONMENT=local
EMPLOYEE_DATA_SOURCE=local_db
```

Employee data then comes from the seeded `data/hr_employee.db`, and
authentication accepts an employee id in place of a token:

```bash
python -m tools.chat_cli dev:employee-001
```

This is for prompt, retrieval and guardrail work only. Three
independent checks keep it out of production — `local_db` is refused
by `Settings.validate_for_production` (the app will not start), by
`LocalDbContextProvider.__init__`, and by the guard in
`IdentityService._offline_principal`.

---

## Tools

```bash
# Can this host reach the HR gateway, and does a real token verify?
# Run this FIRST on any new host.
python -m tools.verify_ejadah_connection <AccessToken> [EmployeeNumber]

# Chat from a terminal, through the real pipeline.
python -m tools.chat_cli <AccessToken> [EmployeeNumber]

# Rebuild the policy vector store.
python -m ingestion.ingest_knowledge_base
```

`verify_ejadah_connection` is the one to reach for when the assistant
answers policy questions but cannot see anyone's leave balance: it
separates a TLS problem from a token problem from a field-name
mismatch, and prints which identity verification layers are actually
active.

The root-level `test_*.py` and `verify_employee_flow.py` scripts are
the original author's scratch files. They predate this rework and
several of them were already stale (`test_chat.py` constructs
`ChatService` with three positional arguments). Use the two tools
above instead.

### Docker

```bash
docker build -t ejadah-hr-assistant .
docker run --rm -p 8000:8000 --env-file .env \
  -v "$PWD/data:/app/data" -v "$PWD/logs:/app/logs" \
  ejadah-hr-assistant
```

The embedding model is baked in at build time, so the container
starts without egress to huggingface.co and the first employee does
not wait for a download.

### Knowledge base

The vector store is committed under `data/vector_db`. To rebuild it
after changing the policy documents in `data/company_info`:

```bash
python -m ingestion.ingest_knowledge_base
```

`GET /ready` reports `vector_store: empty` if this has not been run —
every policy question will answer "not in the knowledge base" until
it has.

---

## API

Everything except `/health` needs the employee's Ejadah access token:

```
Authorization: Bearer <AccessToken>
X-Employee-Id: <EmployeeId>      # optional, cross-checked, never trusted
```

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness. Unauthenticated. |
| GET | `/ready` | Readiness + config audit. Needs `X-Admin-Key`. |
| GET | `/api/me` | Who does this token belong to? |
| POST | `/api/logout` | Stop trusting the token; drop the employee's transcripts. |
| POST | `/api/chat` | Ask a question. `{question, session_id?}` |
| POST | `/api/chat/session` | Mint a new conversation thread id. |
| GET | `/api/chat/sessions` | This employee's threads. |
| GET | `/api/chat/history` | One thread's transcript. |
| DELETE | `/api/chat/history` | Clear one thread. |
| POST | `/api/admin/purge-memory` | Apply the retention window now. Needs `X-Admin-Key`. |

### Socket.IO

The app's primary transport. Same host and port.

```js
io(url, { auth: { token: "<AccessToken>", employee_id: "<EmployeeId>" } })
```

Authentication happens once, in the handshake. A rejected token
refuses the connection rather than connecting and failing later.

| Direction | Event | Payload |
|---|---|---|
| server → | `chat_ready` | `{employee_id, name, designation, department}` |
| → server | `chat` | `{question, session_id}` |
| server → | `chat_typing` | `{typing: bool}` |
| server → | `chat_response` | `{answer, session_id, employee_id, guardrail_status, …tokens}` |
| server → | `chat_error` | `{message, code}` — `code: "unauthorized"` means re-login |
| → server | `clear_session` | `{session_id}` |
| server → | `chat_session_cleared` | `{cleared_session_id, session_id, removed}` |

Tokens travel in the `auth` payload only. Query-string tokens are
ignored deliberately: URLs end up in proxy logs.

---

## Layout

```
api/            FastAPI app, routes, Socket.IO, DI container
auth/           Thin wrapper turning a token into a Principal
ejadah/         ★ Everything that talks to the Ejadah HR APIs
                  ejadah_client.py          HTTP + envelope + legacy TLS
                  identity_service.py       ★ who is asking (read this)
                  employee_service.py       reads their record
                  ejadah_context_builder.py renders it for the prompt
                  ejadah_routes.py          read-only route allow-list
chat/           The pipeline: guard → route → retrieve → generate → guard
employee/       Intent detection, and the provider seam (API vs local db)
guardrails/     Injection, scope, output guard, PII scrubbing
prompts/        System prompts
retriever/ embeddings/ vectordb/ chunking/ loaders/ indexing/  RAG
memory/         Conversation storage + retention
session/        Session id validation and employee scoping
config/ core/   Settings, logging, errors, TTL cache
```

---

## Security notes

Things a reviewer should check, and where they live:

**Identity.** `ejadah/identity_service.py`. Token claims, live
upstream verification, token binding. Also `_guard_owner` in
`ejadah/employee_service.py`, which discards a record whose employee
number does not match the caller even if the gateway returned it.

**Read-only by construction.** `ejadah/ejadah_routes.py` holds an
allow-list of read endpoints, and `EjadahClient.post` refuses
anything outside it. `applyLeaveRequest`, `changePassword` and every
other mutating HR route are unreachable from here, so a prompt
injection cannot cause an action.

**Session scoping.** `session/session_manager.py`. Conversation
memory is keyed by the verified employee number, so passing another
employee's session id returns an empty thread, not their messages.

**Output.** `guardrails/output_guard.py` blocks an answer that names
another employee, leaks a credential or recites the system prompt,
and masks identifier-shaped numbers.

**Data minimisation.** `ejadah/ejadah_context_builder.py` includes
only the sections the question touches. Personal documents are gated
behind an explicit ask and partially masked. Salary is not read at
all — the assistant says so and points at the Payslip screen.

**Logging.** `core/logging_config.py` redacts bearer tokens, and
questions/answers/records are logged only under `DEBUG`, which
`production` refuses.

**Retention.** `MEMORY_RETENTION_DAYS` (default 90). Applied at
startup and via `/api/admin/purge-memory`. `/api/logout` drops the
employee's transcripts immediately, which matters on shared handsets.

### Two things to action before go-live

1. **Rotate `GROQ_API_KEY`.** A working key was committed in `.env`
   in this repository. Treat it as public: revoke it in the Groq
   console, issue a new one, and inject it as an environment variable
   rather than a file. `.env` is now in `.gitignore`, but that does
   not un-publish what git already has — the key needs purging from
   history too.

2. **Ask Ejadah for a token-introspection endpoint.** One route that
   takes the bearer token with an empty body and returns the owning
   employee number. Set `EJADAH_IDENTITY_ROUTE` to its name and
   identity verification becomes exact instead of an echo check. Full
   reasoning in `ejadah/identity_service.py`.

### Scaling

`WORKERS=1`. The rate limiter (`api/rate_limiter.py`) and the
verified-token cache (`core/ttl_cache.py`) are in-process, so a
second worker doubles the effective rate limit and halves the cache
hit rate. Moving both to a shared store is the prerequisite for
scaling out; until then, scale by running more instances only if the
rate limit is enforced upstream.

Prompts include the employee's own HR data, which makes the LLM
provider a data processor. A zero-retention agreement is worth having
before this carries real employee records.
