"""JD parsing package."""

from .batch import parse_jd_batch
from .single import parse_jd

__all__ = ["parse_jd", "parse_jd_batch"]
