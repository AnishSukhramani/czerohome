"""Tests for scripts/predeploy.py (stdlib unittest only)."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minimal_framer.html"


def load_predeploy_module():
    spec = importlib.util.spec_from_file_location("predeploy", ROOT / "scripts" / "predeploy.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pd = load_predeploy_module()


def base_meta() -> dict:
    return json.loads((ROOT / "site.meta.json").read_text())


class PredeployTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name)
        shutil.copy(FIXTURE, self.work / "index.html")
        meta = base_meta()
        (self.work / "site.meta.json").write_text(json.dumps(meta, indent=2))

    def _patch_paths(self, meta_override: dict | None = None):
        index = self.work / "index.html"
        meta_path = self.work / "site.meta.json"
        if meta_override is not None:
            meta_path.write_text(json.dumps(meta_override, indent=2))

        def load_meta():
            return json.loads(meta_path.read_text())

        return mock.patch.multiple(
            pd,
            INDEX=index,
            META_PATH=meta_path,
            load_meta=load_meta,
        )

    def test_idempotent_sanitize(self):
        meta = base_meta()
        html = FIXTURE.read_text()
        once = pd.sanitize(html, meta)
        twice = pd.sanitize(once, meta)
        self.assertEqual(once, twice)

    def test_badge_stripped(self):
        meta = base_meta()
        out = pd.sanitize(FIXTURE.read_text(), meta)
        for token in pd.BANNED_BODY_TOKENS:
            self.assertNotIn(token, out)

    def test_json_ld_uses_repo_url_and_os(self):
        meta = base_meta()
        out = pd.sanitize(FIXTURE.read_text(), meta)
        head = out.split("</head>", 1)[0]
        ld = pd.parse_json_ld_from_head(head)
        app = pd.software_application_from_ld(ld)
        self.assertIsNotNone(app)
        assert app is not None
        self.assertEqual(app["codeRepository"], meta["repo_url"])
        self.assertEqual(app["operatingSystem"], "macOS, Linux")
        self.assertIn(meta["repo_url"], app["sameAs"])
        self.assertIn(meta["demoVideoUrl"], app["sameAs"])

    def test_analytics_off_by_default(self):
        meta = base_meta()
        out = pd.sanitize(FIXTURE.read_text(), meta)
        self.assertNotIn(pd.ANALYTICS_START, out)
        self.assertNotIn("/_vercel/insights/script.js", out)

    def test_analytics_vercel_when_meta_enabled(self):
        meta = base_meta()
        meta["analytics"] = {"vercel": True, "umami": {"enabled": False}}
        out = pd.sanitize(FIXTURE.read_text(), meta)
        self.assertIn(pd.ANALYTICS_START, out)
        self.assertIn("/_vercel/insights/script.js", out)
        self.assertIn("window.va", out)

    def test_analytics_vercel_via_env(self):
        meta = base_meta()
        meta["analytics"] = {"vercel": False, "umami": {"enabled": False}}
        with mock.patch.dict(os.environ, {"CZ_ANALYTICS": "1"}):
            self.assertTrue(pd.vercel_analytics_enabled(meta))
            out = pd.sanitize(FIXTURE.read_text(), meta)
        self.assertIn("/_vercel/insights/script.js", out)

    def test_analytics_env_can_disable(self):
        meta = base_meta()
        meta["analytics"] = {"vercel": True, "umami": {"enabled": False}}
        with mock.patch.dict(os.environ, {"CZ_ANALYTICS": "0"}):
            self.assertFalse(pd.vercel_analytics_enabled(meta))
            out = pd.sanitize(FIXTURE.read_text(), meta)
        self.assertNotIn("/_vercel/insights/script.js", out)

    def test_umami_attributes(self):
        meta = base_meta()
        meta["analytics"] = {
            "vercel": False,
            "umami": {
                "enabled": True,
                "website_id": "abc-123",
                "src": "https://cloud.umami.is/script.js",
                "domains": "construct-zero.vercel.app",
            },
        }
        out = pd.sanitize(FIXTURE.read_text(), meta)
        self.assertIn('data-website-id="abc-123"', out)
        self.assertIn('data-domains="construct-zero.vercel.app"', out)
        self.assertIn("https://cloud.umami.is/script.js", out)

    def test_toggle_analytics_removes_block(self):
        meta = base_meta()
        meta_on = dict(meta)
        meta_on["analytics"] = {"vercel": True, "umami": {"enabled": False}}
        html = pd.sanitize(FIXTURE.read_text(), meta_on)
        meta_off = dict(meta)
        meta_off["analytics"] = {"vercel": False, "umami": {"enabled": False}}
        html_off = pd.sanitize(html, meta_off)
        self.assertNotIn(pd.ANALYTICS_START, html_off)

    def test_cta_warn_vs_strict(self):
        meta = base_meta()
        html = pd.sanitize(FIXTURE.read_text(), meta)
        failures, warnings = pd.issues(html, meta, strict=False)
        self.assertFalse(failures)
        self.assertTrue(any("Community CTA missing" in w for w in warnings))

        html_with_cta = html.replace(
            "</body>",
            f'<a href="{meta["cta"]["community_url"]}">Join</a></body>',
        )
        failures2, warnings2 = pd.issues(html_with_cta, meta, strict=False)
        self.assertFalse(failures2)
        self.assertFalse(warnings2)

        failures3, _ = pd.issues(html, meta, strict=True)
        self.assertTrue(any("Community CTA missing" in f for f in failures3))

    def test_meta_without_new_keys_backward_compatible(self):
        legacy = {
            k: v
            for k, v in base_meta().items()
            if k not in ("analytics", "cta", "repo_url", "demoVideoUrl")
        }
        out = pd.sanitize(FIXTURE.read_text(), legacy)
        self.assertNotIn(pd.ANALYTICS_START, out)
        app = pd.software_application_from_ld(pd.parse_json_ld_from_head(out.split("</head>")[0]))
        self.assertEqual(app["codeRepository"], legacy["github"])

    def test_check_exit_codes(self):
        with self._patch_paths():
            html = (self.work / "index.html").read_text()
            cleaned = pd.sanitize(html, base_meta())
            (self.work / "index.html").write_text(cleaned)
            with mock.patch.object(sys, "argv", ["predeploy.py"]):
                rc = pd.main()
            self.assertEqual(rc, 0)

            (self.work / "index.html").write_text(FIXTURE.read_text())
            with mock.patch.object(sys, "argv", ["predeploy.py", "--check"]):
                rc_check = pd.main()
            self.assertEqual(rc_check, 1)

            (self.work / "index.html").write_text(cleaned)
            with mock.patch.object(sys, "argv", ["predeploy.py", "--check"]):
                rc_ok = pd.main()
            self.assertEqual(rc_ok, 0)


class RealIndexTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / "index.html").exists(), "index.html missing")
    def test_real_index_idempotent(self):
        meta = base_meta()
        original = (ROOT / "index.html").read_text()
        once = pd.sanitize(original, meta)
        twice = pd.sanitize(once, meta)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
