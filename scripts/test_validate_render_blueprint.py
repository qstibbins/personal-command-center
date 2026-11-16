#!/usr/bin/env python3
"""Fixture-based regression tests for render.yaml structural validation."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from validate_render_blueprint import (  # noqa: E402
    API_DEPLOY_ANCHOR_MOUNT,
    API_DEPLOY_ANCHOR_NAME,
    BLUEPRINT,
    validate_blueprint,
)


def _load_repo_blueprint() -> dict:
    data = yaml.safe_load(BLUEPRINT.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _api(data: dict) -> dict:
    for svc in data["services"]:
        if svc.get("name") == "pcc-api":
            return svc
    raise AssertionError("pcc-api missing")


class ValidateRenderBlueprintTests(unittest.TestCase):
    def test_repo_blueprint_passes(self):
        self.assertEqual(validate_blueprint(_load_repo_blueprint()), [])

    def test_rejects_missing_num_instances(self):
        data = _load_repo_blueprint()
        del _api(data)["numInstances"]
        errors = validate_blueprint(data)
        self.assertTrue(any("numInstances" in e for e in errors))

    def test_rejects_scaled_api(self):
        data = _load_repo_blueprint()
        _api(data)["numInstances"] = 2
        errors = validate_blueprint(data)
        self.assertTrue(any("numInstances" in e for e in errors))

    def test_rejects_missing_disk(self):
        data = _load_repo_blueprint()
        del _api(data)["disk"]
        errors = validate_blueprint(data)
        self.assertTrue(any("deploy-anchor disk" in e for e in errors))

    def test_rejects_wrong_mount_path(self):
        data = _load_repo_blueprint()
        _api(data)["disk"]["mountPath"] = "/tmp/wrong"
        errors = validate_blueprint(data)
        self.assertTrue(any(API_DEPLOY_ANCHOR_MOUNT in e for e in errors))

    def test_rejects_wrong_disk_name(self):
        data = _load_repo_blueprint()
        _api(data)["disk"]["name"] = "other-disk"
        errors = validate_blueprint(data)
        self.assertTrue(any(API_DEPLOY_ANCHOR_NAME in e for e in errors))

    def test_keeps_private_api_and_migrate_checks(self):
        data = _load_repo_blueprint()
        mutated = copy.deepcopy(data)
        _api(mutated)["type"] = "web"
        errors = validate_blueprint(mutated)
        self.assertTrue(any("pserv" in e for e in errors))

        mutated = copy.deepcopy(data)
        del _api(mutated)["preDeployCommand"]
        for svc in mutated["services"]:
            if svc.get("name") == "pcc-web":
                svc["preDeployCommand"] = "alembic upgrade head"
        errors = validate_blueprint(mutated)
        self.assertTrue(any("preDeployCommand" in e for e in errors))
        self.assertTrue(any("must not run migrations" in e for e in errors))


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
