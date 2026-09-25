import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request
from unittest.mock import patch

from server import api_server


class AdminMetricsTests(unittest.TestCase):
    def test_dashboard_counts_detail_map_requests_and_recent_login(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(api_server, "DB_PATH", Path(temp_dir) / "metrics.db"):
                api_server.init_db()
                server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.NinganjuHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    base_url = f"http://127.0.0.1:{server.server_port}"

                    def post(path, data, headers=None):
                        payload = json.dumps(data).encode("utf-8")
                        http_request = request.Request(
                            base_url + path, payload,
                            {"Content-Type": "application/json", **(headers or {})},
                            method="POST",
                        )
                        with request.urlopen(http_request) as response:
                            return json.load(response)

                    login = post("/api/login", {"username": "xiaoning", "password": "12345678"})
                    with api_server.get_connection() as conn:
                        conn.execute(
                            """
                            insert into rent_preference
                            (id, user_nickname, work_address, budget_min, budget_max,
                             commute_range, priority, markdown_prompt, created_at)
                            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            ("test-preference", "xiaoning", "新街口", 1500, 2800,
                             "1-15", "balanced", "", api_server.utc_now()),
                        )
                    detail = post(
                        "/api/profile/detail-view",
                        {"preferenceId": "test-preference", "areaName": "新街口微社区"},
                        {"Authorization": f"Bearer {login['sessionToken']}"},
                    )
                    self.assertTrue(detail["success"])

                    api_server.increment_metric("area_evaluation")
                    with patch.object(api_server.request, "urlopen", return_value=None) as urlopen:
                        api_server.open_amap_url("https://restapi.amap.com/v3/place/around", timeout=12)
                        urlopen.assert_called_once()
                    post("/api/metrics/amap-client-call", {}, {"Origin": "http://127.0.0.1:5173"})

                    dashboard = post("/api/admin-dashboard", {})
                    self.assertEqual(dashboard["todayMetrics"], {
                        "siteVisits": 1,
                        "newRegistrations": 0,
                        "areaEvaluations": 9,
                        "detailViews": 1,
                        "workflowCalls": 1,
                        "amapApiCalls": 2,
                    })
                    self.assertEqual(dashboard["recentLogins"][0]["username"], "xiaoning")
                    self.assertEqual(dashboard["recentLogins"][0]["recommendationCount"], 1)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
