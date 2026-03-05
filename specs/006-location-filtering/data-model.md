# Data Model: Location Filtering

**Feature Branch**: `006-location-filtering`
**Status**: Implemented

Core location entities (Location, JobLocation) are defined in [docs/data-model/location.md](../../docs/data-model/location.md).

This document covers data structures specific to the location filtering feature.

## CountryNormalizationResult (value object, not persisted)

Domain value object returned by `normalize_country()`. Drives the conservative country assignment policy required by FR-006.

| Field | Type | Description |
|-------|------|-------------|
| `country_code` | string or None | Resolved ISO alpha-2 code |
| `confidence` | enum | `high`, `low`, or `none` |
| `source` | enum | `explicit_field`, `geonames_match`, `pycountry_match`, `unknown` |
| `is_ambiguous` | bool | True when input could map to multiple countries or is a broad region |
| `multi_country_detected` | bool | True when input contains multiple distinct countries |
| `matched_country_codes` | list[str] | All candidate country codes found during resolution |

**Key behavior**: When `is_ambiguous=True` or `multi_country_detected=True`, `country_code` is set to `None`. This prevents false country assignments on inputs like "CA" (California vs Canada) or "Remote - US or Canada".

## MatchLocationRead (API response shape)

Flattened location payload returned per result item in matching recommendations. Joins `JobLocation` and `Location` fields into a single object.

| Field | Type | Description |
|-------|------|-------------|
| `source_raw` | string or None | Original ATS location text |
| `workplace_type` | string or None | `onsite`, `remote`, `hybrid` |
| `remote_scope` | string or None | Geographic remote scope |
| `is_primary` | bool | Whether this is the primary location |
| `city` | string or None | From `Location` |
| `region` | string or None | From `Location` |
| `country_code` | string or None | From `Location` |
| `display_name` | string or None | From `Location` |

## Country Prefiltering (query-time)

The `build_sql_prefilter` function generates a SQL EXISTS subquery when `preferred_country_code` is provided:

```sql
EXISTS (
  SELECT 1 FROM job_locations jl
  JOIN locations l ON jl.location_id = l.id
  WHERE jl.job_id = j.id AND l.country_code = $N
)
```

This uses the normalized `locations.country_code` — not raw text — ensuring prefiltering is consistent with the conservative normalization policy.

## SQLPrefilterSummary (response metadata)

Included in `MatchResponseMeta` to let callers verify whether country filtering was applied (FR-005).

| Field | Type | Description |
|-------|------|-------------|
| `sponsorship_filter_applied` | bool | |
| `degree_filter_applied` | bool | |
| `preferred_country_code` | string or None | Echo of the requested country, or None |
| `user_degree_rank` | int | |
