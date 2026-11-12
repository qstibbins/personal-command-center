# Personal Command Center (PCC) — Product Vision and Requirements

**Status:** Living product specification  
**Last updated:** 2026-11-09  
**Basis:** PCC discussions in ChatGPT and the existing development handoff. This document describes product intent, not proof that a capability has been implemented.

## 1. Vision

Build a personal, AI-enabled **Command Center**: a durable second brain, capture inbox, knowledge system, and operational hub that helps turn ideas, conversations, research, commitments, and decisions into organized information and useful action.

PCC should not merely collect notes or present an AI chatbot. It should help its owner **remember context, find relevant information, follow through on work, and see what automated workflows have done**. It should reduce dependence on any single AI provider or conversation history as the sole repository of important knowledge.

This is also a hands-on engineering learning project: develop stronger skills in full-stack architecture, data engineering, AI integrations, background processing, security, and deployment through building a useful real system.

## 2. Product principles

1. **One persistent system of record.** PCC owns its structured captures, tasks, projects, knowledge, agent-run records, and outputs. External apps are interfaces or data sources, not the only place this information exists.
2. **Multiple entry points.** Capture and inspect information directly on the PCC website; where supported, use the **standard ChatGPT app (including iPhone)** or other existing assistant clients to issue instructions to PCC. Do not require a custom PCC mobile app for basic conversational interaction.
3. **Capture first, organize progressively.** Make it easy to save raw material without demanding a perfect category or structure at entry time.
4. **Keep provenance.** Preserve original source content, timestamps, and links between derived knowledge and its source. Distinguish a brainstormed possibility from a decision, and a proposed task from an approved commitment.
5. **Visible execution.** Future agent activity must be inspectable: what ran, why, its status, its outputs, errors, and actions requiring approval.
6. **Human control.** Review consequential interpretations and actions; use explicit permission boundaries, especially for changes in external services.
7. **Portable, provider-flexible architecture.** Avoid hard-wiring the entire system to OpenAI or any one model. Allow alternative API providers and, eventually, local models where feasible.
8. **Privacy and security from the first deployment.** Personal information and connected accounts require authentication, protected APIs, least-privilege integrations, secure secrets, and backups.
9. **Ship vertical slices.** Build, verify, deploy, and improve small useful capabilities rather than waiting for the entire vision to be complete.

## 3. Primary user experiences

### A. PCC website: capture and operations

- Enter text or a URL through a web capture form.
- Review captured items in an Inbox, including their source, processing status, and timestamps.
- Later: browse/search knowledge; manage tasks and projects; inspect agent runs, thread/workstream histories, reports, and generated outputs.
- Website capture remains a first-class feature even if conversational capture becomes available.

### B. Standard AI assistant app: conversational control

Desired experience: open the **ordinary ChatGPT app on an iPhone or web**, describe an idea or request, and—through an authorized integration where the client supports it—have the assistant call PCC to save, retrieve, or act on information. Then inspect results on the PCC website.

Examples of *future desired* commands:
- “Save this idea to PCC and associate it with my entrepreneurship project.”
- “What decisions have I made about my graduate education?”
- “Run my weekly briefing and show me what needs attention.”
- “Research these options, save the findings, and let me review them.”

**Important distinction:** PCC calling an AI model API does **not** automatically make PCC accessible from the standard ChatGPT app. The reverse direction requires a supported ChatGPT integration (for example, an authenticated tool/MCP-style interface where available). Verify client availability, mobile support, and permissions before promising this workflow. An existing ChatGPT subscription does not automatically grant API credits or direct access to all conversations and memory.

### C. Background processing and specialized agents

As the platform matures, workflows may classify captures, extract potential tasks, summarize research, prepare briefings, and coordinate specialized agents. Execution should continue independently of the interface that initiated it, within defined authorization boundaries.

### D. Historical knowledge import

Much valuable context already exists in ChatGPT conversations. PCC should support importing an available ChatGPT data export, preserving original conversations and source metadata, and deriving **reviewable** structured knowledge. Do not assume the export includes all saved/inferred memory, or that ChatGPT exposes automatic full-history synchronization.

## 4. Core product domains

| Domain | Desired capability | Notes |
|---|---|---|
| Universal Capture | Save text and URLs; later additional sources | Website and authorized assistant interfaces |
| Inbox | Review new material and processing state | A capture is not automatically a task |
| Knowledge | Search, retrieve, link, summarize, and trace sources | Retain originals and provenance |
| Tasks | Extract, create, track, and complete actions | Review inferred tasks before commitment |
| Projects | Group captures, tasks, decisions, and outputs by ongoing objective | Cross-cutting contexts are expected |
| Threads / workstreams | Track a continuing topic or initiative over time | Distinct from a ChatGPT conversation and from an agent run |
| Agents | Specialized workers with defined permissions and responsibilities | Future capability |
| Runs / execution history | Record one invocation, status, inputs, outputs, errors, and approvals | Needed for observability and troubleshooting |
| Integrations | Connect external apps and AI providers securely | Explicit OAuth/API authorization where supported |
| Briefings / dashboards | Surface status, priorities, agent activity, and outputs | Built from real persisted data |

### Distinguishing agents, threads, and runs

- **Agent:** A configured specialized capability/worker, such as research or planning.
- **Thread/workstream:** A continuing line of work, such as career development or a product idea; it may involve multiple agents and runs.
- **Run:** A particular execution of a task or workflow, with a status and traceable outputs.

These concepts are **requirements for future design**, not claims that their database models or screens exist today.

## 5. Example areas of use

- Career and graduate education planning, including decisions, options, and research.
- Business/entrepreneurship ideas and follow-up work.
- Personal planning, routines, reminders, and projects.
- Technical learning, software architecture notes, and ongoing development work.
- Research and knowledge synthesis across conversations, documents, and web sources.

These are illustrative domains, not a commitment to implement every integration or workflow in the first release.

## 6. What exists today (reported, not independently inspected)

As of the latest Cursor report:
- Next.js / React web application and FastAPI backend with PostgreSQL persistence.
- Text/URL capture API and an Inbox listing captures.
- Web form successfully saved a capture in an earlier browser test.
- Cursor subsequently implemented pending, success, error, and reset behavior; reported passing frontend lint, four action tests, and production build.
- **The updated form has not yet passed browser acceptance testing.**
- Redis/RQ infrastructure exists, but AI processing and agent orchestration are not yet implemented.

The repository, test runs, and browser checks remain the authoritative implementation evidence.

## 7. Release boundaries

### First private deployment (v0.1)

- Reliable website capture and Inbox, including appropriate validation and feedback.
- Basic automated tests and browser acceptance checks.
- Authentication and protection of both UI and API.
- Secure production configuration, HTTPS, persistent database, backups, migrations, and health checks.
- A usable, private deployed URL; data survives service restarts.

**Not required for v0.1:** specialized agents, multi-agent dashboard, complete ChatGPT history import, ChatGPT mobile integration, or AI-generated task extraction.

### After first deployment

- Verify a supported and secure way to invoke PCC from ChatGPT, especially the standard mobile app.
- Historical conversation import and knowledge review.
- Background processing and AI workflows, followed by visible agent runs, threads, and outputs.

Sequence and acceptance criteria live in `docs/ROADMAP.md`.

## 8. Open questions (do not silently assume answers)

- What ChatGPT integration mechanisms are available for the user's actual client/account, particularly on iPhone?
- Which historical export formats and metadata can PCC reliably import?
- Which external subscriptions/services should connect first, and with what permissions?
- Which AI operations should use external APIs versus local models, and what spending limits apply?
- What approval rules apply to autonomous actions, notifications, and external writes?
- What is the minimum useful definition of a thread/workstream, and how should it relate to imported conversations?

## 9. Maintaining this document

Update this file when **product goals or requirements change**. Do not re-order milestones merely because a future capability was discussed. Record implementation progress in `ROADMAP.md` and the exact next action in `HANDOFF.md`; document technical reality in `ARCHITECTURE.md`.
