"""
Integration tests for Job API endpoints (T021).

Covers:
- POST /api/v1/jobs — create with source_id resolution from legacy source string
- POST /api/v1/jobs — create with explicit source_id
- POST /api/v1/jobs — 422 when legacy source string cannot be resolved
- GET /api/v1/jobs/{job_id} — read response exposes source_id alongside legacy source
- GET /api/v1/jobs — list returns source_id on each item
"""

from fastapi.testclient import TestClient


class TestCreateJob:
    """Integration tests for POST /api/v1/jobs endpoint."""

    def _create_source(
        self, client: TestClient, name: str = "Job Test Source", identifier: str = "job-test-source"
    ) -> dict:
        """Helper: create a source and return its data dict."""
        response = client.post(
            "/api/v1/sources",
            json={
                "name": name,
                "platform": "greenhouse",
                "identifier": identifier,
            },
        )
        assert response.status_code == 201
        return response.json()["data"]

    def test_create_job_resolves_source_id_from_legacy_source(self, client: TestClient):
        """Creating a job with a legacy source string auto-resolves source_id."""
        source = self._create_source(client)

        response = client.post(
            "/api/v1/jobs",
            json={
                "source": "greenhouse:job-test-source",
                "external_job_id": "ext-resolve-1",
                "title": "Software Engineer",
                "apply_url": "https://example.com/apply/1",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["source"] == "greenhouse:job-test-source"
        assert data["source_id"] == source["id"]
        assert data["title"] == "Software Engineer"

    def test_create_job_with_explicit_source_id(self, client: TestClient):
        """Creating a job with explicit source_id keeps it as-is."""
        source = self._create_source(client, name="Explicit Source", identifier="explicit-source")

        response = client.post(
            "/api/v1/jobs",
            json={
                "source": "greenhouse:explicit-source",
                "source_id": source["id"],
                "external_job_id": "ext-explicit-1",
                "title": "Product Manager",
                "apply_url": "https://example.com/apply/2",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["source_id"] == source["id"]

    def test_create_job_unresolvable_source_fails(self, client: TestClient):
        """Creating a job with an unknown source string returns 422."""
        response = client.post(
            "/api/v1/jobs",
            json={
                "source": "nonexistent:platform",
                "external_job_id": "ext-bad-1",
                "title": "Ghost Job",
                "apply_url": "https://example.com/apply/ghost",
            },
        )

        assert response.status_code == 422

    def test_create_job_with_unknown_explicit_source_id_fails(self, client: TestClient):
        """Creating a job with explicit unknown source_id returns 422."""
        response = client.post(
            "/api/v1/jobs",
            json={
                "source_id": "00000000-0000-0000-0000-000000000000",
                "source": "greenhouse:anything",
                "external_job_id": "ext-bad-source-id-1",
                "title": "Ghost Job",
                "apply_url": "https://example.com/apply/ghost-id",
            },
        )

        assert response.status_code == 422
        assert "source_id" in str(response.json()["detail"])


class TestReadJob:
    """Integration tests for GET /api/v1/jobs and GET /api/v1/jobs/{job_id}."""

    def _seed_job(
        self, client: TestClient, name: str, identifier: str, ext_id: str
    ) -> tuple[dict, str]:
        """Helper: create a source + job, return (job_data, source_id)."""
        source_resp = client.post(
            "/api/v1/sources",
            json={
                "name": name,
                "platform": "lever",
                "identifier": identifier,
            },
        )
        source_data = source_resp.json()["data"]

        job_resp = client.post(
            "/api/v1/jobs",
            json={
                "source": f"lever:{identifier}",
                "source_id": source_data["id"],
                "external_job_id": ext_id,
                "title": "Data Scientist",
                "apply_url": "https://example.com/apply/ds",
            },
        )
        assert job_resp.status_code == 201
        return job_resp.json(), source_data["id"]

    def test_get_job_exposes_source_id(self, client: TestClient):
        """GET /api/v1/jobs/{job_id} response includes source_id."""
        job_data, source_id = self._seed_job(client, "Get Source", "get-source", "ext-get-1")
        job_id = job_data["id"]

        response = client.get(f"/api/v1/jobs/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["source_id"] == source_id
        assert "lever:" in data["source"]

    def test_list_jobs_exposes_source_id(self, client: TestClient):
        """GET /api/v1/jobs list response includes source_id on each item."""
        job_data, source_id = self._seed_job(client, "List Source", "list-source", "ext-list-1")

        response = client.get("/api/v1/jobs")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        matching = [j for j in data if j["id"] == job_data["id"]]
        assert len(matching) == 1
        assert matching[0]["source_id"] == source_id
