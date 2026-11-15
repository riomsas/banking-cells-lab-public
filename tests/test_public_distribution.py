"""Public distribution inventory and secret-pattern checks.

This test protects the reviewed Community Edition file inventory.
It is not a substitute for pre-publication review of repository history.
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {
    ".github/workflows/lab-tests.yml",
    ".gitignore",
    "LICENSE",
    "NOTICE",
    "README.md",
    "SECURITY.md",
    "app/__init__.py",
    "app/__main__.py",
    "app/api.py",
    "app/cells.py",
    "app/platform.py",
    "app/web/app.css",
    "app/web/app.js",
    "app/web/assets/favicon.svg",
    "app/web/index.html",
    "tests/browser-e2e.cjs",
    "tests/test_cells.py",
    "tests/test_http_live.py",
    "tests/test_migrations.py",
    "tests/test_platform.py",
    "tests/test_public_distribution.py",
    "tests/test_service_domains.py",
}
SECRET_RULES = {
    "private-key-block": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    "github-token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}"),
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "generic-api-key": re.compile(r"sk-[A-Za-z0-9]{32,}"),
}
MAX_FILE_SIZE = 120_000


class PublicDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT, capture_output=True, check=True,
        )
        cls.files = sorted(
            path.decode("utf-8") for path in result.stdout.split(b"\0") if path
        )

    def test_inventory_is_explicit(self):
        self.assertEqual(set(self.files), ALLOWED,
                         "Distribution inventory changed; review before publication")

    def test_only_expected_file_types(self):
        for path in self.files:
            with self.subTest(path=path):
                item = ROOT / path
                self.assertTrue(item.is_file())
                self.assertLessEqual(item.stat().st_size, MAX_FILE_SIZE)
                self.assertFalse(item.is_symlink())
                item.read_text(encoding="utf-8")

    def test_no_embedded_credential_patterns(self):
        for path in self.files:
            text = (ROOT / path).read_text(encoding="utf-8")
            for label, rule in SECRET_RULES.items():
                with self.subTest(path=path, detection=label):
                    self.assertIsNone(rule.search(text),
                                      f"Potential embedded credential in {path}: {label}")

    def test_no_external_runtime_import(self):
        content = (ROOT / "app/api.py").read_text(encoding="utf-8")
        self.assertIn('("127.0.0.1",', content)
        self.assertNotIn('("0.0.0.0",', content)


if __name__ == "__main__":
    unittest.main()
