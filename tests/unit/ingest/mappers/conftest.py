from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def mapper_output_contract_fields(required_mapper_output_fields: tuple[str, ...]) -> tuple[str, ...]:
    return required_mapper_output_fields


@pytest.fixture
def assert_mapper_contract(assert_mapper_output_contract):
    return assert_mapper_output_contract
