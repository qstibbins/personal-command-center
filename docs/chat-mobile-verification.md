# Chat mobile verification checklist (Phase 1A.2 PR5)

Architecture / ops: [`chat-architecture.md`](chat-architecture.md), ADR [`decisions/0005-provider-neutral-chat.md`](decisions/0005-provider-neutral-chat.md).

Automated Vitest coverage exercises conversation selection, history ordering,
streaming updates, stop/cancel, duplicate-send prevention, partial/failed
messages, HTTP 409 `run_in_progress`, and empty/loading/error states.

The following items require a **real iPhone Safari or iOS Simulator** check
(Chrome device-mode alone is insufficient per architecture §G2 / §J.3).

## Setup

1. Sign in with the allowlisted Google account.
2. Open `/chat` on iPhone Safari or the iOS Simulator.
3. Confirm mock-only replies (no paid provider keys required).

## Checklist

| Check | Expected |
|---|---|
| Safe-area (home indicator) | Composer sits above the home indicator; bottom padding uses `env(safe-area-inset-bottom)`. |
| Dynamic viewport (`dvh`) | Chat shell fills the visible viewport; CSS declares `100vh` then `100dvh` so supporting browsers prefer dynamic height; composer is not trapped under Safari chrome. |
| Composer font size | Textarea renders at ≥16px; focusing it does **not** trigger iOS page zoom. |
| Keyboard — focus | Focusing the composer keeps the latest message and input visible (scroll into view). |
| Keyboard — send | After send, the new turn remains visible above the keyboard. |
| Portrait list/thread | Conversation list is full-width; opening a chat shows the thread with a back control. |
| Landscape / iPad | Sidebar (~280px) + transcript layout; no horizontal overflow while streaming. |
| Touch targets | New chat / Send / Stop / conversation rows are comfortable to tap (≥44px). |
| Streaming layout | Incremental tokens do not cause horizontal scroll or large layout jumps. |
| Stop | Stop ends generation; partial assistant text remains labeled Interrupted. |

## Deterministic streaming / Stop validation (`PCC_MOCK_STREAM_TEST`)

Normal production mock echo finishes too quickly to observe progressive tokens.
Use the API env flag documented in [`deploy/render-runbook.md`](deploy/render-runbook.md) §4a.

| Step | Action | Expected |
|---|---|---|
| 1 | On **pcc-api**, set `PCC_MOCK_STREAM_TEST=true` and **redeploy** the API | New instance live; `PCC_ENV=production` unchanged |
| 2 | iPhone: new chat, send short `hi` | Assistant text grows for ~8–12s (`STREAM-TEST: …`) |
| 3 | Press **Stop** mid-stream | Generation stops; no further growth |
| 4 | Navigate away and back / refresh | Partial assistant message still stored |
| 5 | Send another short message | New reply streams; no stuck `run_in_progress` |
| 6 | Set `PCC_MOCK_STREAM_TEST=false` (or delete) on **pcc-api** and **redeploy** | `hi` returns quick `Echo: hi` again |

Enabling or disabling the flag **requires an API redeploy**. Web rebuild is not required for this flag alone.

## Out of scope for this checklist

- Real AI providers, model pickers, attachments, PWA install, production multi-process claims.
- PR3 still requires exactly one non-overlapping `pcc-api` process.
