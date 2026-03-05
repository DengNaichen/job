"""Contract tests for location hard-cut API schemas."""

from app.schemas.job import JobCreate, JobRead, JobUpdate
from app.schemas.match import MatchResultItem


def test_job_schemas_drop_legacy_location_fields() -> None:
    # Read contract: no compatibility location_text field.
    assert "location_text" not in JobRead.model_fields

    # Write contract: no legacy location fields accepted.
    for field_name in (
        "location_text",
        "location_city",
        "location_region",
        "location_country_code",
        "location_workplace_type",
        "location_remote_scope",
    ):
        assert field_name not in JobCreate.model_fields
        assert field_name not in JobUpdate.model_fields


def test_matching_result_schema_uses_normalized_location_shape_only() -> None:
    # Removed flattened legacy location fields.
    for field_name in (
        "location_text",
        "city",
        "region",
        "country_code",
        "workplace_type",
    ):
        assert field_name not in MatchResultItem.model_fields

    # New normalized location payload is required in result contract.
    assert "locations" in MatchResultItem.model_fields


def test_matching_result_schema_forbids_silent_legacy_extras() -> None:
    assert MatchResultItem.model_config.get("extra") == "forbid"
