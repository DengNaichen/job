"""Skills alignment domain component."""

from .alias_builder import AliasBuildStats, build_alias_table
from .aligner import (
    AlignmentStats,
    align_skill_entries,
    align_skills_from_files,
    load_alias_table,
    read_raw_skills,
    write_aligned_skill_entries,
)
from .normalization import normalize_skill_text

__all__ = [
    "AliasBuildStats",
    "AlignmentStats",
    "align_skill_entries",
    "align_skills_from_files",
    "build_alias_table",
    "load_alias_table",
    "normalize_skill_text",
    "read_raw_skills",
    "write_aligned_skill_entries",
]

