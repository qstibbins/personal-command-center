# syntax=docker/dockerfile:1
# Production Next.js image for Render web service (ADR 0004).
# Build context MUST be the repository root (see render.yaml dockerContext).
# Uses Next.js standalone output for a smaller runtime footprint on ~512MB plans.

FROM node:22-bookworm-slim AS deps

WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.11.0 --activate

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json

RUN pnpm install --frozen-lockfile --filter @pcc/web...


FROM node:22-bookworm-slim AS builder

WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.11.0 --activate

# pnpm uses a content-addressable store + symlinks; copy the whole workspace install.
COPY --from=deps /app ./
COPY apps/web ./apps/web

# Placeholder auth env so `next build` can evaluate Auth.js config without secrets.
# These values are NOT used at runtime and must be overridden by Render env vars.
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production \
    AUTH_SECRET=build-time-placeholder-not-for-runtime \
    AUTH_URL=https://build.invalid \
    AUTH_GOOGLE_ID=build-time-placeholder \
    AUTH_GOOGLE_SECRET=build-time-placeholder \
    PCC_ALLOWED_GOOGLE_EMAILS=build@example.com \
    PCC_SERVICE_CREDENTIAL=build-time-placeholder

RUN pnpm --filter @pcc/web build


FROM node:22-bookworm-slim AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    # Keep Node heap under typical Render starter RAM (512MB) with headroom for OS.
    NODE_OPTIONS=--max-old-space-size=384

RUN groupadd --system --gid 10001 nodejs \
    && useradd --system --uid 10001 --gid nodejs --home /app --shell /usr/sbin/nologin nextjs

# Standalone tracing root is the monorepo; server entry lives under apps/web.
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "apps/web/server.js"]
