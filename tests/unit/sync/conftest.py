from __future__ import annotations

import pytest

from app.models import PlatformType, Source


def _make_source(
    identifier: str,
    platform: PlatformType = PlatformType.GREENHOUSE,
) -> Source:
    return Source(
        name=identifier.title(),
        name_normalized=identifier,
        platform=platform,
        identifier=identifier,
    )


@pytest.fixture
def source_factory():
    return _make_source
