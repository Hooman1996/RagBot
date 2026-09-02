from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class ImmediateRunner:
    def __init__(self):
        self.calls = []

    async def run(self, function, /, *args, **kwargs):
        kwargs.pop("wait_for_completion_on_cancel", None)
        self.calls.append((function, args))
        return function(*args)


class ExistingLoginCompatibilityTests(unittest.TestCase):
    def test_existing_login_state_is_reused_without_new_credentials(self):
        from evaluation_system.backend.app.ragbot_auth import (
            establish_ragbot_user,
            require_ragbot_user,
        )
        authenticated = {
            "id": 41,
            "username": "existing-user",
            "role": "user",
        }
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        establish_ragbot_user(request, authenticated)
        self.assertIs(require_ragbot_user(request), authenticated)
        main_source = Path("main.py").read_text(encoding="utf-8")
        self.assertIn("authentication_service.authenticate", main_source)
        self.assertIn("establish_ragbot_user(request, user)", main_source)
        self.assertNotIn("EVAL_ADMIN_API_TOKEN_SHA256", main_source)


class EvaluationRouteTests(unittest.TestCase):
    def test_control_plane_and_built_frontend_mount_together(self):
        try:
            from fastapi import APIRouter, FastAPI
            from evaluation_system.backend.app.integration import (
                install_evaluation_routes,
            )
        except ImportError as exc:
            self.skipTest(f"evaluation API dependency is unavailable: {exc}")

        with tempfile.TemporaryDirectory() as directory:
            dist = Path(directory)
            (dist / "index.html").write_text(
                "<html><body>evaluation-ui</body></html>",
                encoding="utf-8",
            )
            app = FastAPI()
            control_plane = APIRouter(prefix="/api/v1/evaluation")

            @control_plane.get("/system/database-status")
            async def database_status_probe():
                return {"status": "READY"}

            installed = install_evaluation_routes(
                app,
                SimpleNamespace(enabled=True),
                frontend_dist=dist,
                control_plane_router=control_plane,
            )
            self.assertTrue(installed)
            included = [
                route.original_router
                for route in app.routes
                if hasattr(route, "original_router")
            ]
            self.assertIn(control_plane, included)
            control_paths = {route.path for route in control_plane.routes}
            self.assertIn("/api/v1/evaluation/system/database-status", control_paths)
            paths = {getattr(route, "path", "") for route in app.routes}
            self.assertIn("/evaluation", paths)
            main_source = Path("main.py").read_text(encoding="utf-8")
            self.assertIn("install_evaluation_routes(", main_source)
            self.assertIn('Path(__file__).resolve().parent', main_source)

    def test_database_setup_requires_existing_ragbot_login(self):
        try:
            from fastapi import HTTPException
            from evaluation_system.backend.app.api import system
            from evaluation_system.backend.app.ragbot_auth import (
                require_ragbot_user,
            )
        except ImportError as exc:
            self.skipTest(f"evaluation API dependency is unavailable: {exc}")

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        with self.assertRaises(HTTPException) as caught:
            require_ragbot_user(request)
        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(
            caught.exception.detail["error_code"], "RAGBOT_AUTH_REQUIRED"
        )
        initialize_route = next(
            route
            for route in system.router.routes
            if route.path == "/system/database-initialize"
        )
        dependency_calls = {
            dependency.call
            for dependency in initialize_route.dependant.dependencies
        }
        self.assertIn(require_ragbot_user, dependency_calls)


class EvaluationEnvironmentTests(unittest.TestCase):
    def test_root_environment_controls_operational_settings(self):
        from evaluation_system.backend.app.config import get_settings

        values = {
            "EVAL_ENABLED": "true",
            "EVAL_API_HOST": "127.0.0.9",
            "EVAL_API_PORT": "8190",
            "EVAL_REDIS_URL": "redis://internal-redis:6380/4",
            "EVAL_USE_CELERY": "false",
            "EVAL_ALLOW_DB_INIT": "true",
            "EVAL_SESSION_CONCURRENCY": "3",
            "EVAL_REPEAT_MAX": "27",
            "EVAL_CELERY_POOL": "solo",
            "EVAL_CELERY_CONCURRENCY": "2",
        }
        get_settings.cache_clear()
        try:
            with patch.dict(os.environ, values, clear=False):
                settings = get_settings()
                self.assertTrue(settings.enabled)
                self.assertEqual(settings.api_host, "127.0.0.9")
                self.assertEqual(settings.api_port, 8190)
                self.assertEqual(settings.redis_url, values["EVAL_REDIS_URL"])
                self.assertFalse(settings.use_celery)
                self.assertTrue(settings.allow_db_init)
                self.assertEqual(settings.session_concurrency, 3)
                self.assertEqual(settings.repeat_max, 27)
                self.assertEqual(settings.celery_pool, "solo")
                self.assertEqual(settings.celery_concurrency, 2)
        finally:
            get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
