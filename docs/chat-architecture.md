# Provider-neutral chat — documentation index

**Status:** Phase 1A.2 PR1–PR5 on `main`; ADR **0005 Accepted**  
**Decision record:** [`docs/decisions/0005-provider-neutral-chat.md`](decisions/0005-provider-neutral-chat.md)  
**Living verified map:** [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) Part A  
**Mobile checklist:** [`docs/chat-mobile-verification.md`](chat-mobile-verification.md)  
**Deploy ops (single-worker chat):** [`docs/deploy/render-runbook.md`](deploy/render-runbook.md) §3

## Topology (implemented)

```
Browser (/chat UI, Auth.js cookie)
  → Next.js BFF (/api/chat/*)
  → Private FastAPI (/api/v1/chat/*)
  → Orchestrator → MockProvider → PostgreSQL
```

Do **not** call FastAPI from the browser. Do **not** scale `pcc-api` for chat without a multi-worker abort redesign.

## Feature matrix

| Capability | Classification |
|---|---|
| Conversations/messages/runs schema + Alembic | Implemented and tested |
| MockProvider + `ProviderAdapter` contract | Implemented and tested |
| Claim / SSE stream / finalize / 409 / cancel / recovery | Implemented and tested |
| Authenticated Next.js BFF + SSE proxy | Implemented and tested |
| Responsive `/chat` UI, Send/Stop, streamId isolation | Implemented and unit-tested |
| Real iPhone Safari / Simulator acceptance (§J.3) | Implemented UI; **not** end-to-end device-verified in CI |
| Real OpenAI / Anthropic / Gemini providers | Planned |
| Provider/model selection UI | Planned |
| ChatGPT conversation-history import | Planned (schema hooks only) |
| MCP tool gateway / write-tool approvals | Planned |
| Multi-worker cancel & recovery | Operationally unsupported |
| Second allowlisted chat user | Operationally unsupported until HMAC/`user.id` binding |
| Production chat “ready” claim / M3.5c | Not complete (owner Render + ops + Safari) |

## Environment variables (chat-related)

| Variable | Role |
|---|---|
| `PCC_SERVICE_CREDENTIAL` | BFF → FastAPI Authorization (also captures) |
| `API_INTERNAL_URL` / `API_INTERNAL_HOSTPORT` | Private API base |
| `PCC_DEFAULT_CHAT_PROVIDER` | Default `mock` |
| `PCC_CHAT_ASSUME_SINGLE_WORKER` | Recovery **gate** only — not process enforcement |

## Where to read next

1. ADR 0005 — decision, lifecycle, security, SSE, ops limits, extensions  
2. `ARCHITECTURE.md` — verified endpoints, tables, frontend tree  
3. `chat-mobile-verification.md` — manual Safari/Simulator checklist  
4. `render-runbook.md` §3 — single-process deploy constraints  
