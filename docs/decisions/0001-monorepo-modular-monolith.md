# ADR 0001 — Monorepo and modular monolith

**Status:** Accepted for v0.1

## Context
The project needs a Next.js frontend, Python API, background processing, and a single coherent domain model. It is a personal application and learning project.

## Decision
Use one repository, with `apps/web` and `apps/api`. Run HTTP and background worker processes from the same Python package. Organize backend code by business capability as features are implemented.

## Consequences
- Simpler integration and deployment than microservices.
- Python and TypeScript remain separate language environments.
- Future service extraction remains possible but is not assumed.
