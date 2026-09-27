"""The protected HTML, served assets, API and page renderer form one release."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

import main
from analytics_metrics import aggregate_analytics
from frontend_paths import STATIC_DIR
from tests.test_analytics import NOW, SyntheticDatabase, postgres_connect, sample_rows
from tests.test_web_auth import login, setup
from versioned_assets import VERSIONED_ASSETS, asset_digest


def _local_path(url):
    return urlsplit(url).path


def test_served_analytics_page_assets_api_and_render_path(setup, monkeypatch, postgres_connect, tmp_path):
    setup.users[1]["role"] = "admin"
    populated_db = SyntheticDatabase(postgres_connect, sample_rows())
    monkeypatch.setattr(setup, "get_connection", populated_db.get_connection, raising=False)
    monkeypatch.setattr(main, "aggregate_analytics", lambda db, days: aggregate_analytics(db, days, NOW))
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        page = client.get("/analytics")
        assert page.status_code == 200
        assert "no-store" in page.headers["cache-control"]
        assert page.headers["pragma"] == "no-cache"
        soup = BeautifulSoup(page.text, "html.parser")
        root = soup.select_one("#analyticsRoot")
        assert root["data-analytics-contract"] == "main-analytics/v3"
        assert [node.get_text(strip=True) for node in soup.select(".chart-card__title")] == [
            "Queries per day", "Feedback outcomes", "Conversation depth",
            "Completion duration", "Users who queried per day", "Query states",
            "Weekday comparison", "Weekday × hour activity",
        ]
        assert soup.select_one(".chart-row.three-cards") is not None
        css = (STATIC_DIR / "css/analytics.css").read_text(encoding="utf-8")
        assert "grid-template-columns: repeat(3, 1fr)" in css
        assert ".chart-row.three-cards > .chart-card:last-child { grid-column: span 2; }" in css
        assert ".chart-row.three-cards > .chart-card:last-child { grid-column: span 1; }" in css
        bootstrap = soup.select("script:not([src])")[-1].string
        assert "browser script version mismatch" in bootstrap
        card_ids = [node["id"] for node in soup.select("#analyticsRoot canvas")]
        assert card_ids == ["chartQueriesDay", "chartFeedback", "chartDepth", "chartDuration",
                            "chartUsersDay", "chartStates", "chartWeekly"]
        asset_nodes = soup.select("script[src], link[rel=stylesheet]")
        assets = [node.get("src") or node.get("href") for node in asset_nodes]
        integrity_by_url = {node.get("src") or node.get("href"): node.get("integrity")
                            for node in asset_nodes}
        served_script = None
        seen = set()
        for asset in assets:
            path = _local_path(asset)
            if not path.startswith("/static/_v/"):
                continue  # local vendor Chart.js stays unversioned
            match = re.fullmatch(r"/static/_v/([0-9a-f]{64})/(.+)", path)
            assert match, path
            digest, relative = match.groups()
            assert relative in VERSIONED_ASSETS
            assert digest == asset_digest(relative)
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
            assert hashlib.sha256(response.content).hexdigest() == digest
            expected_integrity = "sha256-" + base64.b64encode(hashlib.sha256(response.content).digest()).decode()
            assert integrity_by_url[asset] == expected_integrity
            seen.add(relative)
            if relative == "js/analytics.js":
                served_script = response.text
                assert "Heatmap data unavailable" not in served_script
                assert 'const CONTRACT_VERSION = "main-analytics/v3"' in served_script
                assert "chartFeedback" in served_script and "chartWeekly" in served_script
                invalid = path.replace(digest, "0" * 64 if digest != "0" * 64 else "1" * 64, 1)
                assert client.get(invalid).status_code == 404
        assert seen == {"css/base.css", "css/app.css", "css/analytics.css",
                        "css/web_controls.css", "js/web_auth.js", "js/analytics.js"}
        assert served_script is not None
        assert any("vendor/chart.js/4.5.1/chart.umd.js" in asset for asset in assets)

        populated = client.get("/api/analytics?days=7")
        assert populated.status_code == 200
        assert populated.json()["meta"]["contract_version"] == root["data-analytics-contract"]
        assert populated.json()["kpis"]["total_queries"] > 0
        empty_db = SyntheticDatabase(postgres_connect, [])
        monkeypatch.setattr(setup, "get_connection", empty_db.get_connection, raising=False)
        empty = client.get("/api/analytics?days=7")
        assert empty.status_code == 200
        assert empty.json()["kpis"]["total_queries"] == 0

    bundle = tmp_path / "served_analytics.json"
    bundle.write_text(json.dumps({
        "html": page.text, "script": served_script, "bootstrap": bootstrap,
        "cardIds": card_ids,
        "populated": populated.json(), "empty": empty.json(),
    }), encoding="utf-8")
    env = os.environ.copy()
    env["ANALYTICS_SERVED_BUNDLE"] = str(bundle)
    result = subprocess.run(
        ["node", "--test", "tests/analytics.frontend.test.cjs"],
        cwd=Path(__file__).resolve().parents[1], env=env,
        text=True, capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# tests 7" in result.stdout


def test_asset_digest_changes_with_content(monkeypatch):
    import versioned_assets
    current = versioned_assets.asset_bytes("js/analytics.js")
    original = asset_digest("js/analytics.js")
    monkeypatch.setattr(versioned_assets, "asset_bytes", lambda _path: current + b"changed")
    assert versioned_assets.asset_digest("js/analytics.js") != original
