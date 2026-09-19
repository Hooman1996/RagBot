from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch


class ImmediateRunner:
    def __init__(self):
        self.calls = []

    async def run(self, function, /, *args, **kwargs):
        kwargs.pop("wait_for_completion_on_cancel", None)
        self.calls.append((function, args))
        return function(*args)


class ExistingLoginCompatibilityTests(unittest.TestCase):
    def test_existing_login_contract_has_no_evaluation_state_bridge(self):
        main_source = Path("main.py").read_text(encoding="utf-8")
        self.assertIn("authentication_service.authenticate", main_source)
        self.assertIn('raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")', main_source)
        self.assertNotIn("establish_ragbot" + "_user", main_source)
        self.assertNotIn("ragbot" + "_authenticated" + "_user", main_source)
        self.assertNotIn("EVAL_ADMIN_API_TOKEN_SHA256", main_source)


class EvaluationRouteTests(unittest.TestCase):
    def test_ragbot_owns_only_the_permanent_evaluation_contract(self):
        main_source = Path("main.py").read_text(encoding="utf-8")

        self.assertIn("app.include_router(internal_evaluation_router)", main_source)
        self.assertIn('@app.get("/api/documents")', main_source)
        self.assertNotIn("evaluation_system.backend", main_source)
        self.assertNotIn("embedded_integration", main_source)
        self.assertNotIn("install_evaluation_routes", main_source)
        self.assertNotIn('app.mount("/evaluation"', main_source)
        self.assertFalse(Path("evaluation_system/embedded_integration.py").exists())


class EvaluationEnvironmentTests(unittest.TestCase):
    def test_environment_controls_operational_settings(self):
        from evaluation_system.backend.app.config import get_settings

        values = {
            "EVAL_ENABLED": "true",
            "EVAL_API_HOST": "127.0.0.9",
            "EVAL_API_PORT": "8190",
            "EVAL_SSE_POLL_INTERVAL_SECONDS": "0.75",
            "EVAL_ALLOW_DB_INIT": "true",
            "EVAL_SESSION_CONCURRENCY": "3",
            "EVAL_REPEAT_MAX": "27",
            "EVAL_WORKER_POLL_INTERVAL_SECONDS": "0.25",
            "EVAL_WORKER_STALE_AFTER_SECONDS": "301",
        }
        get_settings.cache_clear()
        try:
            with patch.dict(os.environ, values, clear=False):
                settings = get_settings()
                self.assertTrue(settings.enabled)
                self.assertEqual(settings.api_host, "127.0.0.9")
                self.assertEqual(settings.api_port, 8190)
                self.assertEqual(settings.sse_poll_interval_seconds, 0.75)
                self.assertTrue(settings.allow_db_init)
                self.assertEqual(settings.session_concurrency, 3)
                self.assertEqual(settings.repeat_max, 27)
                self.assertEqual(settings.worker_poll_interval_seconds, 0.25)
                self.assertEqual(settings.worker_stale_after_seconds, 301)
        finally:
            get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
