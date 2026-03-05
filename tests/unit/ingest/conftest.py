from __future__ import annotations

from typing import Any

import pytest

REQUIRED_MAPPER_OUTPUT_FIELDS = (
    "external_job_id",
    "title",
    "apply_url",
    "source_id",
    "location_hints",
)


@pytest.fixture(scope="session")
def required_mapper_output_fields() -> tuple[str, ...]:
    return REQUIRED_MAPPER_OUTPUT_FIELDS


@pytest.fixture
def assert_mapper_output_contract(required_mapper_output_fields: tuple[str, ...]):
    def _assert(mapped_job: Any) -> dict[str, Any]:
        payload = mapped_job.model_dump() if hasattr(mapped_job, "model_dump") else dict(mapped_job)
        missing = [field for field in required_mapper_output_fields if field not in payload]

        assert not missing, f"Missing required mapper output fields: {missing}"
        assert isinstance(
            payload["location_hints"], list
        ), "Expected location_hints to be a list for mapper output contract"

        return payload

    return _assert
