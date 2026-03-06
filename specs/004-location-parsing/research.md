# Research: Location Parsing Alignment (004)

## Scope

Audit the current location parsing, normalization, persistence, and response contracts so `004` documentation can align to the code that already ships on this branch.

## Inputs Reviewed

- Spec: [specs/004-location-parsing/spec.md](/Users/nd/Developer/job/specs/004-location-parsing/spec.md)
- Shared location data model: [docs/data-model/location.md](/Users/nd/Developer/job/docs/data-model/location.md)
- Parser and normalization:
  - [app/services/domain/job_location.py](/Users/nd/Developer/job/app/services/domain/job_location.py)
  - [app/services/domain/country_normalization.py](/Users/nd/Developer/job/app/services/domain/country_normalization.py)
  - [app/services/domain/geonames_resolver.py](/Users/nd/Developer/job/app/services/domain/geonames_resolver.py)
- Snapshot persistence path:
  - [app/services/application/full_snapshot_sync/location_sync.py](/Users/nd/Developer/job/app/services/application/full_snapshot_sync/location_sync.py)
- Public schemas and downstream consumers:
  - [app/schemas/job.py](/Users/nd/Developer/job/app/schemas/job.py)
  - [app/schemas/location.py](/Users/nd/Developer/job/app/schemas/location.py)
  - [app/schemas/match.py](/Users/nd/Developer/job/app/schemas/match.py)
  - [app/api/v1/jobs.py](/Users/nd/Developer/job/app/api/v1/jobs.py)
  - [app/services/infra/matching/query.py](/Users/nd/Developer/job/app/services/infra/matching/query.py)
  - [app/services/infra/matching/llm_rerank.py](/Users/nd/Developer/job/app/services/infra/matching/llm_rerank.py)
- Source mapper implementations:
  - [app/ingest/mappers/ashby.py](/Users/nd/Developer/job/app/ingest/mappers/ashby.py)
  - [app/ingest/mappers/greenhouse.py](/Users/nd/Developer/job/app/ingest/mappers/greenhouse.py)
  - [app/ingest/mappers/lever.py](/Users/nd/Developer/job/app/ingest/mappers/lever.py)
  - [app/ingest/mappers/eightfold.py](/Users/nd/Developer/job/app/ingest/mappers/eightfold.py)
  - [app/ingest/mappers/smartrecruiters.py](/Users/nd/Developer/job/app/ingest/mappers/smartrecruiters.py)
  - [app/ingest/mappers/apple.py](/Users/nd/Developer/job/app/ingest/mappers/apple.py)
  - [app/ingest/mappers/tiktok.py](/Users/nd/Developer/job/app/ingest/mappers/tiktok.py)
  - [app/ingest/mappers/uber.py](/Users/nd/Developer/job/app/ingest/mappers/uber.py)
- Focused tests:
  - [tests/unit/test_job_location.py](/Users/nd/Developer/job/tests/unit/test_job_location.py)
  - [tests/unit/services/domain/test_geonames_resolver.py](/Users/nd/Developer/job/tests/unit/services/domain/test_geonames_resolver.py)
  - [tests/unit/ingest/mappers/test_ashby.py](/Users/nd/Developer/job/tests/unit/ingest/mappers/test_ashby.py)
  - [tests/unit/ingest/mappers/test_greenhouse.py](/Users/nd/Developer/job/tests/unit/ingest/mappers/test_greenhouse.py)
  - [tests/unit/ingest/mappers/test_lever.py](/Users/nd/Developer/job/tests/unit/ingest/mappers/test_lever.py)
  - [tests/unit/ingest/mappers/test_eightfold.py](/Users/nd/Developer/job/tests/unit/ingest/mappers/test_eightfold.py)
  - [tests/unit/ingest/mappers/test_smartrecruiters.py](/Users/nd/Developer/job/tests/unit/ingest/mappers/test_smartrecruiters.py)
  - [tests/unit/ingest/mappers/test_company_apis.py](/Users/nd/Developer/job/tests/unit/ingest/mappers/test_company_apis.py)
  - [tests/unit/sync/test_full_snapshot_sync.py](/Users/nd/Developer/job/tests/unit/sync/test_full_snapshot_sync.py)
  - [tests/location_contract/contract/test_location_schema_contract.py](/Users/nd/Developer/job/tests/location_contract/contract/test_location_schema_contract.py)
  - [tests/location_contract/integration/test_jobs_location_response_contract.py](/Users/nd/Developer/job/tests/location_contract/integration/test_jobs_location_response_contract.py)
  - [tests/location_contract/integration/test_matching_location_response_contract.py](/Users/nd/Developer/job/tests/location_contract/integration/test_matching_location_response_contract.py)
  - [tests/location_contract/behavior/test_location_behavior_guardrails.py](/Users/nd/Developer/job/tests/location_contract/behavior/test_location_behavior_guardrails.py)

## Decision 1: Use current code and focused tests as the source of truth for `004`

Rationale:
- The branch already contains implemented parsing, mapper, sync, and contract behavior.
- The user request is document alignment, not behavior expansion.
- Focused regression coverage for this area is already present and passing.

Alternatives considered:
- Rewrite `004` around an intended future parser: rejected because it would drift from the branch's actual behavior.

## Decision 2: Document the parser as conservative heuristics, not a rich geographic interpreter

Rationale:
- `parse_location_text` only handles a small set of patterns: remote scopes, comma-separated strings, single-country strings, and city-only GeoNames matches.
- `normalize_country` rejects ambiguous broad regions such as `EMEA`, `APAC`, `Europe`, `North America`, and ambiguous non-explicit alpha-2 tokens such as `CA`, `ON`, and US state abbreviations.
- `UK` is normalized to canonical `GB`.
- Remote scopes that are not clearly a single country preserve `remote_scope` text and leave `country_code` unset.

Alternatives considered:
- Describe `004` as explicit multi-country parsing with structured country lists: rejected because no such output exists in the current code.

## Decision 3: Define source normalization as one optional-field contract, not a fully populated uniform payload

Rationale:
- All supported mappers emit `location_hints`, but they do not all populate the same keys.
- Text-driven mappers (`ashby`, `greenhouse`, `lever`, `eightfold`) feed `parse_location_text` and usually emit `source_raw`, `city`, `region`, `country_code`, `workplace_type`, and optional `remote_scope`.
- Structured-field mappers (`smartrecruiters`, `apple`, `tiktok`, `uber`) mostly pass explicit city/region/country values and may omit `workplace_type` or `remote_scope`.
- Snapshot sync coerces missing `workplace_type` to `unknown` and missing strings to `None`, so the durable contract is optional-field and unknown-safe.

Alternatives considered:
- Document every source as producing the exact same required hint shape: rejected because that would overstate current implementation consistency.

## Decision 4: Make snapshot persistence rules explicit in `004`

Rationale:
- Full snapshot sync only persists hints that contain at least one structured field: `city`, `region`, or `country_code`.
- `source_raw` alone is not reparsed during snapshot sync; raw text-only hints are ignored.
- If `city` exists but `country_code` is missing, snapshot sync may use GeoNames to backfill `country_code` and sometimes `region`.
- The first usable structured hint becomes the primary job location.

Alternatives considered:
- Describe sync as reparsing raw location strings during persistence: rejected because that logic is not implemented in the snapshot path.

## Decision 5: Treat downstream normalized-location contracts as completed behavior

Rationale:
- Jobs API returns `locations` and excludes legacy `location_text`.
- Matching API returns `locations` and excludes flattened legacy location fields.
- SQL country prefiltering uses normalized `job_locations -> locations.country_code`, which matches the contract/behavior tests already in the branch.

Alternatives considered:
- Keep legacy response fields in `004` migration language: rejected because the current schemas and tests already enforce the hard cut.

## Current Behavior Inventory

### Parser and country normalization

- Workplace extraction is keyword-based and conservative:
  - `remote`, `fully remote`, `work from home`, `telecommute` => `remote`
  - `hybrid`, `partially remote` => `hybrid`
  - `onsite`, `on-site`, `in office`, `in-office` => `onsite`
  - Otherwise => `unknown`
- Remote scope extraction supports patterns such as `Remote - Canada`, `Remote (Germany)`, and `US - Remote`.
- Single-country remote scopes can set `country_code`; broader scopes preserve `remote_scope` only.
- Country normalization is strict for non-explicit text:
  - ambiguous regions stay unresolved
  - ambiguous alpha-2 abbreviations in non-explicit text stay unresolved
  - exact alpha-2/alpha-3/name matches can normalize
  - fuzzy country matching is only used for explicit source-native country fields
- GeoNames is used conservatively:
  - exact country alias lookup
  - city resolution with country or region hints
  - city-only resolution only when there is a unique or clearly dominant candidate

### Source mapper behavior

- `ashby`, `greenhouse`, `lever`, and `eightfold` rely on `parse_location_text`.
- `smartrecruiters` trusts explicit location object fields and only sets `workplace_type=remote` when `location.remote == true`.
- `apple`, `tiktok`, and `uber` trust explicit location hierarchy fields and normalize country from explicit source fields.
- Mappers generally emit a single location hint, not multiple parsed alternatives.
- Empty or whitespace-only location inputs become `location_hints=[]`.

### Persistence behavior

- Snapshot sync reads `location_hints` only.
- A hint without `city`, `region`, or `country_code` does not create `Location` or `JobLocation` rows.
- Persisted job/location links keep `source_raw`, `workplace_type`, `remote_scope`, and `is_primary`.
- Canonical `Location` rows are deduplicated by `canonical_key`; per-job metadata lives on `JobLocation`.

### API and matching behavior

- Job read payloads expose `locations: list[JobLocationRead]`.
- Matching results expose `locations: list[MatchLocationRead]` and derive `primary_location` internally for rerank context.
- Country filtering in matching uses the normalized country code on linked `Location` rows.
- Existing contract and behavior tests treat ambiguous inputs as `country_code=None`, not as errors.

## Completion Audit (Current State)

- User Story 1: Implemented and covered by parser/behavior tests.
- User Story 2: Implemented for supported mappers, with one important nuance: "same contract" currently means a shared optional-field `location_hints` contract, not identical key population per source.
- User Story 3: Implemented and guarded by schema, integration, and matching behavior tests.

## Evidence Commands (executed)

1. `rg --files | rg '004|docs|README|spec|prd|design|architecture'`
2. `rg -n "location|city|state|country|remote|hybrid|onsite|geo|region" app tests -g '!**/README.md'`
3. `./.venv/bin/pytest tests/unit/test_job_location.py tests/unit/ingest/mappers/test_ashby.py tests/unit/ingest/mappers/test_eightfold.py tests/unit/ingest/mappers/test_greenhouse.py tests/unit/ingest/mappers/test_lever.py tests/unit/ingest/mappers/test_smartrecruiters.py tests/unit/ingest/mappers/test_company_apis.py tests/unit/sync/test_full_snapshot_sync.py tests/location_contract/contract/test_location_schema_contract.py tests/location_contract/integration/test_jobs_location_response_contract.py tests/location_contract/integration/test_matching_location_response_contract.py tests/location_contract/behavior/test_location_behavior_guardrails.py -q`

## Result

All material unknowns for `004` documentation alignment are resolved. The next doc pass should describe the current conservative parser, the optional-field `location_hints` ingestion contract, the snapshot persistence constraints, and the already-enforced normalized response contracts, without implying richer parsing behavior than the branch actually implements.
