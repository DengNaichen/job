# Architecture Diagrams

These diagrams describe the current implemented architecture only.
No planned/target-state model is included in this document.

Related design notes:

- [Content Fingerprint Design](./content-fingerprint.md)
- [Skills Alignment Component (Draft)](./skills-alignment-component.md)
- [Skills Alignment Production Plan](./skills-alignment-production-plan.md)

## 1. System Overview

```mermaid
flowchart LR
    subgraph Upstream["Upstream Sources"]
        GH["Greenhouse"]
        LV["Lever"]
        AS["Ashby"]
        SR["SmartRecruiters"]
        EF["Eightfold"]
        CA["Company APIs<br/>Apple / Uber / TikTok"]
    end

    subgraph Ingest["Ingest Layer"]
        SRC["Source config<br/>platform + identifier"]
        RUNNER["run_scheduled_ingests.py"]
        SYNC["SyncService"]
        TRACK["SyncRunRepository"]
        FULL["FullSnapshotSyncService"]
        F["Fetcher"]
        M["Mapper"]
        BLOBM["JobBlobManager"]
        LOCSYNC["location_sync"]
        EMBREF["EmbeddingRefreshService"]
    end

    subgraph Storage["Storage"]
        PG["PostgreSQL<br/>sources / job / syncrun / locations / job_locations / job_embedding"]
        BLOB["Supabase Storage<br/>description_html / raw_payload blobs"]
    end

    subgraph API["Serving Layer"]
        FAST["FastAPI"]
        SOURCES["/api/v1/sources"]
        JOBS["/api/v1/jobs"]
        MATCH["/api/v1/matching/recommendations"]
    end

    GH --> F
    LV --> F
    AS --> F
    SR --> F
    EF --> F
    CA --> F

    SRC --> RUNNER
    RUNNER --> SYNC
    SYNC --> TRACK
    SYNC --> FULL
    FULL --> F
    FULL --> M
    FULL --> BLOBM
    FULL --> LOCSYNC
    BLOBM --> BLOB
    FULL --> PG
    LOCSYNC --> PG
    TRACK --> PG
    SYNC --> EMBREF
    EMBREF --> PG

    PG --> FAST
    FAST --> SOURCES
    FAST --> JOBS
    FAST --> MATCH
```

## 2. Ingest Sequence

```mermaid
sequenceDiagram
    participant Cron as cron / manual trigger
    participant Runner as run_scheduled_ingests.py
    participant Sync as SyncService
    participant Track as SyncRunRepository
    participant Full as FullSnapshotSyncService
    participant Fetch as Fetcher
    participant Map as Mapper
    participant Blob as JobBlobManager
    participant Store as Supabase Storage
    participant Loc as location_sync
    participant DB as PostgreSQL
    participant Emb as EmbeddingRefreshService

    Cron->>Runner: start ingest batch
    Runner->>Sync: sync_source(source)
    Sync->>Track: get_running_by_source_id(source_id)
    Track-->>Sync: no active run
    Sync->>Track: try_create_running(source_id)
    Sync->>Full: sync_source(source, fetcher, mapper)

    Full->>Fetch: fetch(source.identifier)
    Fetch-->>Full: raw jobs

    loop each raw job
        Full->>Map: map(raw job)
        Map-->>Full: JobCreate payload
    end

    Full->>DB: load existing jobs by source_id

    loop each mapped job (bounded concurrency)
        Full->>Blob: sync_job_blobs(job)
        Blob->>Store: upload_if_missing(html/raw)
        Store-->>Blob: pointer state
    end

    Full->>DB: persist staged jobs
    Full->>Loc: sync_staged_job_locations(...)
    Loc->>DB: upsert locations + job_locations
    Full->>DB: finalize snapshot (close missing open jobs)
    DB-->>Full: commit complete

    Full-->>Sync: SourceSyncResult
    Sync->>Track: finish success / failed

    alt success and not dry-run
        Sync->>Emb: refresh_for_source(source_id, snapshot_run_id)
        Emb->>DB: upsert active-target job_embedding
    end

    Sync-->>Runner: final SyncRun
    Runner-->>Cron: exit code
```

Implementation notes:

- `FullSnapshotSyncService` is split into `app/services/application/full_snapshot_sync/` modules (`mapping`, `staging`, `location_sync`, `finalize`, `service`).
- Blob sync uses bounded concurrency during staging (default concurrency is 8).
- Overlap protection is keyed by `source_id` and backed by a DB partial unique index for running `SyncRun`.

## 3. Current Database Model

- `source_id` is the authoritative owner FK on both `job` and `syncrun`.
- Canonical locations are normalized via `locations` + `job_locations`.
- Large content is pointer-based (`description_html_key`, `raw_payload_key`), with payloads stored in Supabase Storage.
- Legacy physical columns `job.source`, `syncrun.source`, `job.location_text`, `job.description_html`, and `job.raw_payload` are already dropped.

```mermaid
erDiagram
    SOURCE {
        uuid id PK
        string name
        string platform
        string identifier
        boolean enabled
    }

    JOB {
        uuid id PK
        uuid source_id FK
        string external_job_id
        string title
        string apply_url
        string normalized_apply_url
        string status
        string description_html_key
        string description_html_hash
        string raw_payload_key
        string raw_payload_hash
        jsonb structured_jd
        int structured_jd_version
        datetime published_at
        datetime last_seen_at
    }

    SYNC_RUN {
        uuid id PK
        uuid source_id FK
        string status
        datetime started_at
        datetime finished_at
        int fetched_count
        int mapped_count
        int unique_count
        int inserted_count
        int updated_count
        int closed_count
    }

    LOCATION {
        uuid id PK
        string canonical_key
        string display_name
        string country_code
        string region
        string city
        int geonames_id
    }

    JOB_LOCATION {
        uuid id PK
        uuid job_id FK
        uuid location_id FK
        boolean is_primary
        string source_raw
        string workplace_type
        string remote_scope
    }

    JOB_EMBEDDING {
        uuid id PK
        uuid job_id FK
        string embedding_kind
        int embedding_target_revision
        string embedding_model
        int embedding_dim
        vector embedding
        string content_fingerprint
        datetime updated_at
    }

    SOURCE ||--o{ JOB : owns
    SOURCE ||--o{ SYNC_RUN : tracks
    JOB ||--o{ JOB_LOCATION : links
    LOCATION ||--o{ JOB_LOCATION : links
    JOB ||--o{ JOB_EMBEDDING : embeds
```

## 4. Current Matching / Retrieval

Current online matching flow:

- Build one candidate embedding text from profile summary + skills + work history.
- Apply SQL prefilters (sponsorship, degree, optional preferred country via `job_locations -> locations`).
- Run vector recall on active-target `job_embedding`.
- Apply hard filters, then deterministic rerank.
- Optionally apply LLM rerank on top candidates.

```mermaid
flowchart LR
    U["Candidate profile"]
    T["Embedding text builder"]
    E["Candidate embedding"]
    P["SQL prefilters<br/>sponsorship / degree / country"]
    V["Vector recall<br/>job_embedding active target"]
    H["Hard filters"]
    R["Deterministic rerank"]
    L["Optional LLM rerank"]
    O["Top recommendations"]

    U --> T
    T --> E
    E --> V
    P --> V
    V --> H
    H --> R
    R --> O
    R --> L
    L --> O
```
