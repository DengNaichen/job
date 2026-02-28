from __future__ import annotations

import pytest

from app.models.source import PlatformType, build_source_key


def test_build_source_key_uses_platform_and_identifier() -> None:
    assert build_source_key(PlatformType.GREENHOUSE, "airbnb") == "greenhouse:airbnb"


def test_build_source_key_strips_identifier_whitespace() -> None:
    assert build_source_key("greenhouse", "  stripe  ") == "greenhouse:stripe"


def test_build_source_key_rejects_empty_identifier() -> None:
    with pytest.raises(ValueError, match="identifier cannot be empty"):
        build_source_key("greenhouse", "   ")
