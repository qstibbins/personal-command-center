# Provider adapters (Phase 1A)

Provider-neutral chat adapters for Personal Command Center. The orchestrator
(PR3+) talks only to [`ProviderAdapter`](base.py); vendor SDKs stay behind
adapters.

## Contract

| Piece | Location | Notes |
|---|---|---|
| Types + Protocol | `base.py` | Sync `stream(...) -> Iterator[StreamEvent]` |
| Registry | `registry.py` | `get_provider(name)` |
| Mock | `mock.py` | Deterministic echo; no network |

Adapters **must not**:

- Open or hold SQLAlchemy sessions
- Persist conversations / messages / runs
- Perform authentication or ownership checks
- Call other PCC services

Adapters **must**:

- Declare capabilities per model
- Emit normalized `StreamEvent` types (`message_start`, `content_delta`, `usage`, `message_end`, `error`)
- Map vendor errors to normalized `error_code` values (§C3)
- Honor `abort: threading.Event` between chunks (stop promptly; no more deltas)

Optional: implement `complete()` (or use `collect_stream`) for non-stream callers.

`tools=` is accepted for forward compatibility and is always `None` in Phase 1A.

## MockProvider

- Id / model: `mock` / `mock-echo-v1`
- Output: `Echo: ` + last user message, chunked
- Usage: `input_tokens = len(joined_messages)//4`, `output_tokens = len(output)//4`, `cost_micros = 0`
- `MOCK:*` test hooks only when `allow_test_hooks` is true (registry sets this from `pcc_env != production`)
- Optional `PCC_MOCK_STREAM_TEST=true`: fixed `STREAM-TEST: …` body with timed chunks (~10s) for progressive/Stop validation; default off; independent of `MOCK:*` hooks

## Adding OpenAI / Anthropic / Gemini later

1. Add `openai.py` / `anthropic.py` / `google.py` implementing `ProviderAdapter`.
2. Keep streaming **sync** for 1A compatibility: wrap async SDKs with a small
   sync bridge (thread + queue, or vendor sync client), **or** migrate the chat
   path to async SQLAlchemy in a dedicated PR — do not mix silently.
3. Map vendor stream chunks → `StreamEvent`; map HTTP/SDK errors →
   `provider_unavailable` / `rate_limited` / `context_overflow` / etc.
4. Put API keys only in server-side Settings (never required when default
   provider is `mock`). Missing keys must not break API boot.
5. Register the name in `registry.py` / `_KNOWN_PROVIDERS`.
6. Persist `provider` + `model` on assistant messages (orchestrator); do not
   use vendor message IDs as PCC primary keys.
7. Leave tool / vision / multimodal details in `content_parts` or future
   `tool_invocations` — do not expand the 1A wire SSE event set until needed.

No real vendor SDKs ship in Phase 1A PRs.
