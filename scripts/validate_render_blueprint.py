#!/usr/bin/env python3
"""Structural validation for render.yaml (no Render API / no provisioning)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "render.yaml"

API_DEPLOY_ANCHOR_NAME = "pcc-api-deploy-anchor"
API_DEPLOY_ANCHOR_MOUNT = "/var/pcc-deploy-anchor"


def validate_blueprint(data: dict[str, Any]) -> list[str]:
    """Return human-readable errors; empty list means the blueprint is valid."""
    errors: list[str] = []

    services = data.get("services")
    databases = data.get("databases")
    if not isinstance(services, list) or not services:
        errors.append("services list required")
        return errors
    if not isinstance(databases, list) or not databases:
        errors.append("databases list required")
        return errors

    by_name: dict[str, Any] = {}
    for svc in services:
        if not isinstance(svc, dict):
            errors.append("each service must be a mapping")
            continue
        name = svc.get("name")
        if not name or name in by_name:
            errors.append(f"duplicate or missing service name: {name!r}")
            continue
        by_name[name] = svc

    web = by_name.get("pcc-web")
    api = by_name.get("pcc-api")
    if not web or web.get("type") != "web":
        errors.append("pcc-web must be type: web")
    if not api or api.get("type") != "pserv":
        errors.append("pcc-api must be type: pserv (private)")

    for svc in services:
        if isinstance(svc, dict) and svc.get("type") in {
            "worker",
            "keyvalue",
            "redis",
            "cron",
        }:
            errors.append(f"unexpected service type for v0.1: {svc.get('type')}")

    if web and api and web.get("region") != api.get("region"):
        errors.append("web and api must share region for private networking")
    if web and databases and databases[0].get("region") != web.get("region"):
        errors.append("database must share region with services")

    if databases and databases[0].get("ipAllowList") != []:
        errors.append("pcc-db ipAllowList must be [] (private only)")

    if api is not None:
        if "preDeployCommand" not in api:
            errors.append("pcc-api must define preDeployCommand for Alembic")
        if api.get("numInstances") != 1:
            errors.append("pcc-api must set numInstances: 1")
        disk = api.get("disk")
        if not isinstance(disk, dict):
            errors.append("pcc-api must attach the deploy-anchor disk")
        else:
            if disk.get("name") != API_DEPLOY_ANCHOR_NAME:
                errors.append(
                    f"pcc-api disk.name must be {API_DEPLOY_ANCHOR_NAME!r}"
                )
            if disk.get("mountPath") != API_DEPLOY_ANCHOR_MOUNT:
                errors.append(
                    f"pcc-api disk.mountPath must be {API_DEPLOY_ANCHOR_MOUNT!r}"
                )
            size = disk.get("sizeGB")
            if size != 1:
                errors.append("pcc-api disk.sizeGB must be 1")

    if web is not None:
        if "preDeployCommand" in web:
            errors.append(
                "pcc-web must not run migrations (avoid concurrent Alembic)"
            )
        if web.get("healthCheckPath") != "/api/health":
            errors.append("pcc-web healthCheckPath must be /api/health")

    forbidden_substrings = ("sk-", "BEGIN ", "password=", "postgresql://")
    for svc in services:
        if not isinstance(svc, dict):
            continue
        for item in svc.get("envVars") or []:
            if not isinstance(item, dict):
                continue
            if "value" in item and any(
                s in str(item["value"]) for s in forbidden_substrings
            ):
                if item.get("key") in {"NODE_ENV", "PCC_ENV"}:
                    continue
                errors.append(
                    f"suspicious hardcoded env value for {item.get('key')}"
                )
            if item.get("generateValue") and item.get("sync") is False:
                errors.append(
                    f"{item.get('key')}: generateValue and sync:false conflict"
                )

    return errors


def main() -> int:
    raw = BLUEPRINT.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        print("render.yaml must parse to a mapping", file=sys.stderr)
        return 1

    errors = validate_blueprint(data)
    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        return 1

    services = data["services"]
    databases = data["databases"]
    by_name = {svc["name"]: svc for svc in services}
    print("render.yaml structural validation OK")
    print(f"  services: {', '.join(by_name)}")
    print(f"  database: {databases[0].get('name')} plan={databases[0].get('plan')}")
    print(
        "  pcc-api: numInstances=1 "
        f"disk={API_DEPLOY_ANCHOR_NAME}@{API_DEPLOY_ANCHOR_MOUNT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
