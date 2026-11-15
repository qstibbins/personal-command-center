# ADR 0005 — Provider-neutral PCC chat architecture

**Status:** Accepted (Phase 1A.2 PR1–PR5 implemented on `main`; this ADR records the decision and verified shape)  
**Date:** 2026-11-15  
**Implements:** Phase 1A.1 design baseline (Project store `docs/phase-1a1-provider-neutral-chat-architecture.md`) via PRs #13–#17  
**Related:** ADR 0003 (auth), ADR 0004 (Render private FastAPI), `docs/ARCHITECTURE.md`, `docs/chat-mobile-verification.md`, `docs/deploy/render-runbook.md` §3

## Context

PCC needs a ChatGPT-like conversational surface on iPhone, iPad, and desktop that is **owned by PCC**, not locked to a single vendor SDK or ChatGPT thread history. Roadmap Milestone 4 (ChatGPT → PCC tools) remains a separate capture/bridge concern and is **not** a reliable iPhone write path under current OpenAI docs.

Phase 1A therefore delivers a PCC-owned chat stack with:

- A provider-neutral persistence model and adapter contract
- A **deterministic mock provider** (no paid API keys required)
- Auth reuse from ADR 0003 / 0004 (Auth.js allowlist + private FastAPI + service credential)
- A responsive `/chat` UI behind the Next.js BFF

Phase 1A.1 produced the design; Phase 1A.2 landed it as six vertical PRs. This ADR accepts the implemented architecture and documents operational limits that remain binding after merge.

## Decision

Build **PCC-owned chat** as:

```
Browser (Auth.js session cookie only)
   → Next.js public web: /chat UI + /api/chat/* BFF
   → Private FastAPI: /api/v1/chat/* (service principal + chat scopes)
   → Chat orchestrator (claim → stream → finalize)
   → ProviderAdapter (sync Iterator[StreamEvent])
   → MockProvider only (MVP)
   → PostgreSQL (conversations, messages, message_usage, chat_runs)
```

Hard rules for the accepted MVP:

1. Browser never calls FastAPI directly and never holds `PCC_SERVICE_CREDENTIAL` or provider secrets.
2. `owner_email` is derived only from the allowlisted Auth.js session in the BFF.
3. Default provider is **mock**; real OpenAI/Anthropic/Gemini adapters are out of Phase 1A.
4. At most one `chat_runs.status='running'` row per conversation (partial unique index); concurrent send → **HTTP 409** `run_in_progress`.
5. Provider streaming uses a **sync** iterator; DB sessions are short (claim / finalize only) — never held open across stream yields.
6. Chat cancel uses an **in-process** abort registry → **exactly one non-overlapping `pcc-api` process**.

## Alternatives considered

| Option | Why not chosen for Phase 1A |
|---|---|
| Browser → FastAPI direct (CORS + tokens) | Violates ADR 0004 private API; would expose credentials/CORS surface |
| Vendor thread IDs as primary keys | Couples schema to one provider; blocks import/multi-provider |
| WebSockets for streaming | Unnecessary for unidirectional assistant streams; harder through Next proxy on Render |
| Async ORM + async adapters | Mismatch with existing sync SQLAlchemy `SessionLocal` stack |
| Real provider SDKs in the same PRs | Requires secrets and paid APIs; contradicts mock-first MVP |
| Multi-worker Redis abort bus | Deferred; MVP is single-process cancel/recovery |

## Consequences

**Positive**

- Capture Inbox and chat share the same trust boundary (public web, private API).
- Mock-only CI/local paths need no external AI keys.
- Schema and adapter leave clear hooks for real providers, ChatGPT import, and tools later.

**Negative / binding limits**

- Single-process `pcc-api` for chat abort/recovery (see Operational constraints).
- BFF asserts `owner_email` from session email (unsigned claim) — **single allowlisted user only** until stronger identity binding.
- Process crash mid-stream loses unpersisted in-memory assistant buffer (partial/failed recovery finalizes the run, not the missing text).
- Real Safari/iOS Simulator checklist for mobile acceptance remains a manual gate (`docs/chat-mobile-verification.md`).

## Implemented layers (verified)

| Layer | Location | Owns |
|---|---|---|
| Chat UI | `apps/web/app/chat/*` (`/chat`, `/chat/[conversationId]`) | Layout, sidebar/list, transcript, composer, streamId isolation, mobile chrome |
| Web BFF | `apps/web/app/api/chat/*` | Auth.js gate; JSON CRUD proxy; SSE pipe; abort forwarding; session `owner_email` |
| Chat API | `apps/api/src/pcc/api/chat.py` | HTTP contracts; service-principal + `chat:read`/`chat:write` |
| Orchestrator | `services/chat_orchestrator.py`, `chat_conversations.py`, `chat_abort.py`, `chat_recovery.py` | Claim txn, stream, finalize, cancel, abandoned-run recovery |
| Providers | `apps/api/src/pcc/providers/` | `ProviderAdapter` Protocol, `MockProvider`, registry |
| Persistence | Alembic `0005_chat_schema`, `db/models.py` | Provider-neutral tables and invariants |

## Data model

| Table | Role |
|---|---|
| `conversations` | Owner-scoped threads; `title`, `status` (`active`/`archived`/`deleted`), defaults `default_provider`/`default_model`, `next_sequence` allocator, import hooks `source` / `source_external_id` / `source_metadata`, soft delete via `status=deleted` + `deleted_at` |
| `messages` | `role` ∈ `system\|user\|assistant\|tool`; `status` ∈ `complete\|streaming\|partial\|failed` (**no** `cancelled` on messages); unique `(conversation_id, sequence)`; optional import `source_external_id` |
| `message_usage` | Optional 1:1 usage for assistant completions (`input_tokens`, `output_tokens`, …) |
| `chat_runs` | Generation attempts; `status` ∈ `running\|completed\|cancelled\|failed`; `cancel_reason` ∈ `client_stop\|disconnect\|superseded\|null`; **partial unique** one `running` per conversation |

**Sequence allocation:** claim transaction advances `conversations.next_sequence` and assigns message `sequence` values atomically.

**One-running-run invariant:** DB partial unique index `uq_chat_runs_one_running_per_conversation`; claim conflicts surface as HTTP 409 `run_in_progress`.

## Provider adapter contract

Defined in `apps/api/src/pcc/providers/base.py`:

- **`ProviderAdapter` Protocol:** `id()`, `capabilities(model)`, `list_models()`, `stream(...)-> Iterator[StreamEvent]`
- **`StreamEvent` types:** `message_start`, `content_delta`, `usage`, `message_end`, `error`
- **`ProviderCapabilities`:** streaming, tools, vision, system_prompt, max_context_tokens, supports_cancellation
- **`UsageInfo`:** optional token/cost fields (mock reports deterministic counts)
- **Errors:** normalized codes (`provider_unavailable`, `rate_limited`, `cancelled`, `internal`, …). Orchestrator-only code `run_in_progress` must **not** be emitted by adapters.
- **Cancellation:** adapters honor `threading.Event` `abort` between chunks.
- **MVP implementation:** `MockProvider` (`mock` / `mock-echo-v1`) only; `PCC_DEFAULT_CHAT_PROVIDER=mock`.

Future real providers plug in behind the same Protocol without changing message primary keys.

## Conversation lifecycle

1. **Create** conversation (`POST` BFF → FastAPI) for session owner (mock defaults).
2. **Submit message** (`POST …/messages`) with content only; BFF injects `owner_email`.
3. **Claim (short txn):** lock conversation; reject if running; allocate sequences; insert user `complete` + assistant `streaming` + `chat_runs.running`; register abort handle **before** commit; commit; close session.
4. **Stream (no open DB txn):** sync MockProvider yields events; orchestrator maps to SSE (`run_id` / `message_id` on wire).
5. **Finalize (short txn):** persist assistant `complete|partial|failed`, usage, terminal run status; unregister abort handle.
6. **Cancel:** `POST /api/v1/chat/runs/{id}/cancel` (and BFF mirror) sets abort → finalize `messages.status=partial`, `chat_runs.status=cancelled`, `cancel_reason=client_stop` (or disconnect).
7. **Recovery:** abandoned `running` rows with **no** local abort handle are finalized under `PCC_CHAT_ASSUME_SINGLE_WORKER` gate (see ops).
8. **Soft delete:** conversation `status=deleted`; blocked with 409 while a live run is active.

## Security boundaries

| Boundary | Rule (implemented) |
|---|---|
| Website session | Auth.js Google + verified-email allowlist (`PCC_ALLOWED_GOOGLE_EMAILS`) |
| Page/BFF gate | `getAllowlistedSession` / `resolveChatOwner` |
| Owner identity | BFF sets `owner_email` from session email (trim+lower); client-supplied values dropped |
| FastAPI chat auth | Service principal **only** + scopes `chat:read` / `chat:write` |
| Personal API tokens | Capture scopes only — cannot call chat |
| Credentials | `PCC_SERVICE_CREDENTIAL` server-only (never `NEXT_PUBLIC_`) |
| Single-user limit | Unsigned owner email assertion is acceptable for **one** allowlisted user |
| Multi-user hard gate | Before a **second** allowlisted email: require HMAC-signed owner claim or immutable Auth.js `user.id` binding (not implemented) |

## SSE behavior

Wire events (orchestrator → BFF → browser), JSON `data:` payloads:

- `message_start` `{run_id, message_id, role}`
- `content_delta` `{message_id, delta}`
- `usage` `{message_id, …}`
- `message_end` `{message_id, status, finish_reason}`
- `error` `{message_id?, code, message, partial?}`

BFF (`proxyChatSse`): `runtime=nodejs`, `force-dynamic`, `Cache-Control: no-store`, `X-Accel-Buffering: no`; pipes chunks without buffering the full body; forwards browser `AbortSignal`; non-2xx before stream start forwarded as JSON.

UI: `fetch` + ReadableStream parser (`chat-sse.ts`); Stop calls cancel route then aborts; each send has a **`streamId`** so late events after conversation switch cannot re-lock the composer.

**Known gaps:** no SSE resume / `Last-Event-ID`; no automated browser E2E against a live Safari keyboard; BFF has Vitest auth/chunk smokes, not full multi-process cancel integration.

## Operational constraints (binding)

Documented for deployers in `docs/deploy/render-runbook.md` §3 and `docs/deploy/production-env-checklist.md`:

1. **Exactly one non-overlapping `pcc-api` process** for the current abort/recovery model.
2. In-process abort registry cannot signal another worker’s generator.
3. `PCC_CHAT_ASSUME_SINGLE_WORKER` **gates** abandoned-run recovery; it does **not** enforce single-process deployment.
4. Render rolling deploys that overlap old+new API instances are **unsafe** for live chat runs (new process may finalize the old process’s `running` rows).
5. Process crash mid-stream **loses** unpersisted in-flight assistant text; recovery releases the one-running index.
6. Production chat is **not** claimed ready until owner Render cutover (M3.5c), Safari checklist, and single-process ops are satisfied.

## Responsive UI (PR5)

- Routes: `/chat`, `/chat/[conversationId]`; nav links beside Inbox / API tokens.
- Desktop: ~280px conversation list + transcript/composer; mobile: list ↔ thread panes.
- Streaming transcript with user/assistant distinction; Send / Stop; duplicate-send guards.
- **streamId** stale-event isolation after navigation (PR #17 follow-up).
- `viewport-fit=cover`; CSS `100vh` fallback then preferred `100dvh`; composer `font-size: 16px`; `env(safe-area-inset-*)`.
- Manual device checklist: [`docs/chat-mobile-verification.md`](../chat-mobile-verification.md) (real iPhone Safari or Simulator required for Phase 1A mobile acceptance).

## Implemented vs planned

| Item | Status |
|---|---|
| Schema + Alembic `0005_chat_schema` | **Implemented and tested** |
| MockProvider + adapter Protocol | **Implemented and tested** |
| Orchestrator claim/stream/finalize/409/cancel/recovery | **Implemented and tested** (API pytest) |
| Next.js BFF SSE proxy + session owner | **Implemented and tested** (Vitest) |
| `/chat` responsive UI + streamId isolation | **Implemented and tested** (Vitest state/SSE/client); **not** end-to-end verified on real Safari |
| Real OpenAI/Anthropic/Gemini adapters | **Planned** |
| Provider/model picker UI | **Planned** |
| ChatGPT history import | **Planned** (schema hooks only) |
| MCP / tool gateway | **Planned** (stub ToolSpec; zero tools registered) |
| Multi-worker cancel/recovery | **Operationally unsupported** |
| Second allowlisted user | **Operationally unsupported** until stronger identity binding |
| M3.5c live Render provision | **Owner only; not complete** |

## Extension points

- New `ProviderAdapter` implementations + registry entries; keep mock as CI default.
- UI model label exists; full provider/model switching later.
- Import: `conversations.source` / `source_external_id` and message import uniqueness.
- Tools: `ToolSpec` / orchestrator approval policy for write tools (not enforced yet — no tools).
- Multi-worker: external abort lease (Redis) + recovery redesign.
- Multi-user: signed owner claim or Auth.js `user.id` foreign key before expanding allowlist.

## References

- Design baseline: Phase 1A.1 architecture (Project store)
- Code: PRs #13 (schema), #14 (mock adapter), #15 (orchestrator API), #16 (BFF), #17 (UI)
- Ops: `docs/deploy/render-runbook.md`, `docs/deploy/production-env-checklist.md`
- Mobile checklist: `docs/chat-mobile-verification.md`
- Living map: `docs/ARCHITECTURE.md` Part A
