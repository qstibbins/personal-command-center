#!/usr/bin/env python3
"""Structural validation for render.yaml (no Render API / no provisioning)."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "render.yaml"


def main() -> int:
    raw = BLUEPRINT.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        print("render.yaml must parse to a mapping", file=sys.stderr)
        return 1

    services = data.get("services")
    databases = data.get("databases")
    if not isinstance(services, list) or not services:
        print("services list required", file=sys.stderr)
        return 1
    if not isinstance(databases, list) or not databases:
        print("databases list required", file=sys.stderr)
        return 1

    by_name = {}
    for svc in services:
        name = svc.get("name")
        if not name or name in by_name:
            print(f"duplicate or missing service name: {name!r}", file=sys.stderr)
            return 1
        by_name[name] = svc

    web = by_name.get("pcc-web")
    api = by_name.get("pcc-api")
    if not web or web.get("type") != "web":
        print("pcc-web must be type: web", file=sys.stderr)
        return 1
    if not api or api.get("type") != "pserv":
        print("pcc-api must be type: pserv (private)", file=sys.stderr)
        return 1

    # No Redis / workers in v0.1
    for svc in services:
        if svc.get("type") in {"worker", "keyvalue", "redis", "cron"}:
            print(f"unexpected service type for v0.1: {svc.get('type')}", file=sys.stderr)
            return 1

    if web.get("region") != api.get("region"):
        print("web and api must share region for private networking", file=sys.stderr)
        return 1
    if databases[0].get("region") != web.get("region"):
        print("database must share region with services", file=sys.stderr)
        return 1

    if databases[0].get("ipAllowList") != []:
        print("pcc-db ipAllowList must be [] (private only)", file=sys.stderr)
        return 1

    if "preDeployCommand" not in api:
        print("pcc-api must define preDeployCommand for Alembic", file=sys.stderr)
        return 1
    if "preDeployCommand" in web:
        print("pcc-web must not run migrations (avoid concurrent Alembic)", file=sys.stderr)
        return 1

    if web.get("healthCheckPath") != "/api/health":
        print("pcc-web healthCheckPath must be /api/health", file=sys.stderr)
        return 1

    # No hardcoded secret-looking values
    forbidden_substrings = ("sk-", "BEGIN ", "password=", "postgresql://")
    for svc in services:
        for item in svc.get("envVars") or []:
            if not isinstance(item, dict):
                continue
            if "value" in item and any(
                s in str(item["value"]) for s in forbidden_substrings
            ):
                # Allow non-secret literals like "production"
                if item.get("key") in {"NODE_ENV", "PCC_ENV"}:
                    continue
                print(f"suspicious hardcoded env value for {item.get('key')}", file=sys.stderr)
                return 1
            if item.get("generateValue") and item.get("sync") is False:
                print(
                    f"{item.get('key')}: generateValue and sync:false conflict",
                    file=sys.stderr,
                )
                return 1

    print("render.yaml structural validation OK")
    print(f"  services: {', '.join(by_name)}")
    print(f"  database: {databases[0].get('name')} plan={databases[0].get('plan')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
