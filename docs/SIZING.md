# Sizing and Cost Notes

This document tracks current corpus size, source coverage, storage footprint, and rough enrichment cost.

Unless otherwise noted, the numbers below are a live snapshot taken on `2026-03-01` from the local Supabase full ATS sweep.

Important caveat:

- This sweep was still in progress when this snapshot was taken.
- The current corpus numbers below are therefore a lower bound, not the final completed total.
- This sweep includes only the ATS sources currently present in the source-of-truth database:
  `ashby`, `greenhouse`, `lever`, and `smartrecruiters`.
- The newer company API sources (`apple`, `uber`, `tiktok`, `eightfold`) are supported in code but not included in this particular run.

## Current Full-Sweep Snapshot

### Sweep status

- Configured sources: `5,401`
- Sync runs completed successfully: `5,208`
- Sync runs failed: `3`
- Sync runs currently running: `1`
- Sources not started yet: `189`
- Source keys with any jobs loaded so far: `5,207`
- Loaded coverage vs configured sources: `96.4%`
- Sweep start time: `2026-02-28 23:59:31 UTC`
- Snapshot captured roughly `3h 58m` into the run

This wall-clock time should be treated as an unoptimized baseline, not a steady-state expectation.

There is still substantial optimization headroom here, mainly in:

- source-level concurrency
- batch upsert instead of per-job ORM staging
- blob sync parallelism and smarter short-circuiting
- reducing work on historically empty or low-yield sources

At the moment this snapshot was captured, the still-running source was `smartrecruiters:Dominos`.

### Source inventory by platform

| Platform | Configured sources | Success | Failed | Running | Sources with jobs |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ashby` | 1,455 | 1,454 | 1 | 0 | 1,454 |
| `greenhouse` | 2,257 | 2,255 | 2 | 0 | 2,254 |
| `lever` | 1,438 | 1,438 | 0 | 0 | 1,438 |
| `smartrecruiters` | 251 | 61 | 0 | 1 | 61 |

The `smartrecruiters` row above is partial because that platform was still in progress.

## Job Inventory

- Total jobs loaded so far: `235,458`
- Open jobs: `235,458`
- Closed jobs: `0`

By platform:

| Platform | Jobs loaded so far |
| --- | ---: |
| `ashby` | 29,100 |
| `greenhouse` | 98,407 |
| `lever` | 66,536 |
| `smartrecruiters` | 41,415 |

This is already materially larger than the earlier `~10k` remote snapshot and should be treated as the current working sizing baseline.

## Enrichment Coverage

This full sweep was run as ingest only. It did not run structured JD extraction or embedding backfill.

- Jobs with real `structured_jd` content: `0`
- Jobs with embeddings: `0`
- Jobs with `description_html_key`: `234,894`
- Jobs with `raw_payload_key`: `235,458`

Two important notes:

- `structured_jd` uses JSONB, so SQL `IS NOT NULL` is not a valid enrichment coverage check by itself because JSON `null` can still be present.
- Blob offload is active for almost the entire loaded corpus, but the main `job` row still stores large inline fields, so PostgreSQL TOAST usage remains high.

## Supported But Not Included In This Sweep

The codebase now supports several company API sources that are not yet present in the ATS source-of-truth database used for this run.

Live API totals checked on `2026-02-28`:

| Source | Current live jobs | Notes |
| --- | ---: | --- |
| `apple` | 6,343 | Apple Careers API |
| `uber` | 1,195 | Uber Careers API |
| `tiktok` | 3,705 | TikTok Careers API |
| `eightfold:microsoft` | 3,479 | Microsoft on Eightfold |
| `eightfold:nvidia` | 2,217 | NVIDIA on Eightfold |

- Combined incremental job volume from those five supported sources: `16,939`
- Additional enrichment cost for those five at current assumptions: about `$1.29`

`amazon` remains intentionally deferred because its current API behavior is still risky for the full-snapshot reconcile model.

## Database Footprint

Current local Supabase relation sizes:

| Relation | Total size | Heap | TOAST | Indexes |
| --- | ---: | ---: | ---: | ---: |
| `job` | 2476 MB | 211 MB | 2188 MB | 77 MB |
| `sources` | 2408 kB | 1232 kB | 8192 bytes | 1168 kB |
| `syncrun` | 1536 kB | 856 kB | 8192 bytes | 672 kB |

Derived density for the current `job` table:

- Rough total storage per job, including indexes: `10.77 KiB`
- Rough heap + TOAST storage per job: `10.43 KiB`
- Rough index storage per job: `0.33 KiB`
- Rule of thumb: `~105 MB` per `10k` jobs at the current local schema density

The `job` table is already large enough to show the current design tradeoff clearly:

- blob keys are stored, but large payloads are still materially represented inline
- JSONB and text fields still drive very high TOAST usage
- storage optimization is now an engineering concern, not a hypothetical future concern

## Enrichment Cost Model

### Current model configuration

The current `.env` points enrichment to SiliconFlow-hosted Qwen models via an OpenAI-compatible API:

- Structured JD parsing model: `Qwen/Qwen2.5-7B-Instruct`
- Embedding model: `Qwen/Qwen3-Embedding-0.6B`
- Embedding dimension: `1024`

### Prompt and token assumptions

These are estimates, not invoice totals.

They are derived from:

- the current JD parsing prompt structure in `scripts/batch_parse_jd.py` and `app/services/jd_parser.py`
- the current embedding pipeline
- a `~4 chars/token` heuristic

Estimated token volume:

- Structured JD parse input: about `1,198` input tokens per job
- Structured JD parse output: about `80` output tokens per job
- Embedding input: about `1,175` input tokens per job

### Price assumptions

Using the SiliconFlow model pages checked on `2026-02-28`:

- `Qwen/Qwen2.5-7B-Instruct`: `$0.05 / 1M` input tokens and `$0.05 / 1M` output tokens
- `Qwen/Qwen3-Embedding-0.6B`: `$0.01 / 1M` input tokens

Reference pages:

- <https://siliconflow.com/models/Qwen2.5-7B-Instruct>
- <https://siliconflow.com/models/Qwen3-Embedding-0.6B>

### Estimated cost

| Workload | Estimated cost per 10k jobs | Estimated cost for current 235,458-job corpus |
| --- | ---: | ---: |
| Structured JD parsing | `$0.64` | `$15.07` |
| Embedding generation | `$0.12` | `$2.82` |
| Combined | `$0.76` | `$17.89` |

Operationally:

- the token bill is still cheap relative to the engineering cost of ingest reliability
- once this corpus is fully loaded, the main cost driver becomes incremental change, not one-time enrichment
- if the five company API sources above are also onboarded, the combined enrichment total would rise to about `$19.18`

## Practical Read

- The project has already crossed into a real corpus scale: `235k+` jobs before this sweep has even finished.
- `greenhouse` is no longer a small side platform in this dataset; it is currently the largest loaded source family.
- `smartrecruiters` is undercounted in this snapshot because the platform sweep was still in progress.
- The current schema is functionally working, but its storage and ingest characteristics are now visible enough to justify the next round of optimization work.

## Refresh Guidance

Update this document whenever one of these changes materially:

- the current full sweep finishes
- a new platform is onboarded into the source-of-truth database
- a large backfill is run
- model/provider pricing changes
- storage density changes due to schema or indexing changes

`README.md` should stay product-level. Live corpus size, storage footprint, and cost assumptions belong here.
