"""Integration contract checks for jobs location payload shape."""

from uuid import uuid4

from fastapi.testclient import TestClient


def _create_source(client: TestClient, identifier: str) -> dict:
    unique_identifier = f"{identifier}-{uuid4().hex[:8]}"
    unique_name = f"Location Contract Source {uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/sources",
        json={
            "name": unique_name,
            "platform": "greenhouse",
            "identifier": unique_identifier,
        },
    )
    assert response.status_code == 201
    data = response.json()["data"]
    data["identifier"] = unique_identifier
    return data


def _create_job(
    client: TestClient, source_id: str, source_identifier: str, external_job_id: str
) -> dict:
    response = client.post(
        "/api/v1/jobs",
        json={
            "source_id": source_id,
            "source": f"greenhouse:{source_identifier}",
            "external_job_id": external_job_id,
            "title": "Location Contract Engineer",
            "apply_url": "https://example.com/location-contract-1",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_get_job_returns_normalized_locations_without_legacy_location_text(
    client: TestClient,
) -> None:
    source_identifier = "location-contract-source-get"
    source = _create_source(client, source_identifier)
    created = _create_job(client, source["id"], source["identifier"], "location-contract-job-get")

    response = client.get(f"/api/v1/jobs/{created['id']}")
    assert response.status_code == 200
    payload = response.json()

    assert "locations" in payload
    assert "location_text" not in payload


def test_list_jobs_returns_normalized_locations_without_legacy_location_text(
    client: TestClient,
) -> None:
    source_identifier = "location-contract-source-list"
    source = _create_source(client, source_identifier)
    _ = _create_job(client, source["id"], source["identifier"], "location-contract-job-list")

    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) >= 1

    target = next(row for row in rows if row["external_job_id"] == "location-contract-job-list")
    assert "locations" in target
    assert "location_text" not in target
