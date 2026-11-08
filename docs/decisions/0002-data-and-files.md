# ADR 0002 — Structured data and file storage

**Status:** Proposed for capture milestone

Use PostgreSQL for structured application state and migrations. Store uploaded originals outside the database behind a storage abstraction. Begin with local disk; add an S3-compatible implementation when deployment requirements are known.

Do not store private journal content in broad AI retrieval indexes without explicit permission.
