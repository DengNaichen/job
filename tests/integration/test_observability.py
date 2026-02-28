from fastapi.testclient import TestClient

from app.core.monitoring import reset_metrics


class TestObservability:
    def test_health_response_includes_request_id_header(self, client: TestClient) -> None:
        reset_metrics()

        response = client.get("/health")

        assert response.status_code == 200
        assert response.headers["x-request-id"]

    def test_metrics_endpoint_reports_http_activity(self, client: TestClient) -> None:
        reset_metrics()

        health_response = client.get("/health")
        assert health_response.status_code == 200

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

        payload = metrics_response.json()
        assert payload["http"]["requests_total"] >= 1
        assert payload["http"]["status_codes"]["200"] >= 1
        assert payload["http"]["routes"]["GET /health"]["requests_total"] >= 1
