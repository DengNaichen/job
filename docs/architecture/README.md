# Architecture Diagrams

These diagrams capture the current MVP architecture and the next schema direction already reflected in the roadmap.

They are intentionally lightweight:

- good enough for product and engineering discussion
- close to the current codebase
- explicit about where the design is still transitional

Detailed migration specs:

- [Source ID Migration](./source-id-migration.md)

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
        F["Fetcher"]
        M["Mapper"]
        FS["FullSnapshotSyncService"]
        SRUN["SyncRun tracking"]
        RUNNER["run_scheduled_ingests.py"]
    end

    subgraph Storage["Storage"]
        PG["PostgreSQL<br/>sources / job / syncrun"]
        BLOB["Supabase Storage<br/>description_html / raw_payload"]
    end

    subgraph API["Serving Layer"]
        FAST["FastAPI"]
        SOURCES["/api/v1/sources"]
        JOBS["/api/v1/jobs"]
        MATCH["/api/v1/matching/recommendations"]
    end

    subgraph Enrichment["Enrichment / Retrieval"]
        JD["structured_jd extraction"]
        EMB["job embeddings"]
        RET["hard filters + vector recall + rerank"]
    end

    GH --> F
    LV --> F
    AS --> F
    SR --> F
    EF --> F
    CA --> F

    SRC --> RUNNER
    RUNNER --> SRUN
    RUNNER --> FS
    F --> M
    M --> FS
    FS --> PG
    FS --> BLOB
    SRUN --> PG

    PG --> FAST
    FAST --> SOURCES
    FAST --> JOBS
    FAST --> MATCH

    PG --> JD
    JD --> PG
    PG --> EMB
    EMB --> PG[PostgreSQL: job_embedding]
    PG[PostgreSQL: job_embedding] --> RET
    RET --> MATCH
```

## 2. Ingest Sequence

```mermaid
sequenceDiagram
    participant Cron as cron / manual trigger
    participant Runner as run_scheduled_ingests.py
    participant Sync as SyncService
    participant Track as SyncRunRepository
    participant Fetch as Fetcher
    participant Map as Mapper
    participant Full as FullSnapshotSyncService
    participant Blob as JobBlobManager
    participant DB as PostgreSQL
    participant Store as Supabase Storage

    Cron->>Runner: start ingest batch
    Runner->>Sync: sync_source(source)
    Sync->>Track: check running overlap
    Track-->>Sync: none
    Sync->>Track: create running SyncRun
    Sync->>Full: sync_source(source, fetcher, mapper)
    Full->>Fetch: fetch(source.identifier)
    Fetch-->>Full: raw jobs

    loop each raw job
        Full->>Map: map(raw job)
        Map-->>Full: JobCreate payload
    end

    Full->>DB: load existing jobs for same source

    loop each mapped job
        Full->>Blob: sync_job_blobs(job)
        Blob->>Store: upload_if_missing(html / raw)
        Store-->>Blob: pointer state
    end

    Full->>DB: stage inserts / updates
    Full->>DB: close missing jobs for same source
    DB-->>Full: commit complete
    Full-->>Sync: SourceSyncResult
    Sync->>Track: finish success / failed
    Track-->>Runner: final SyncRun
    Runner-->>Cron: exit code
```

## 3. Current Database Shape

`source_id` is the **authoritative owner FK** on both `job` and `syncrun`.
The legacy `source` string field (`platform:identifier`) is dual-written for backward compatibility
and preserved until a future physical rename.

```mermaid
flowchart LR
    S["sources
    ---
    id PK
    name
    platform
    identifier
    enabled"]

    J["job
    ---
    id PK
    source_id FK → sources.id
    source string (compat)
    external_job_id
    title
    apply_url
    location_text
    description_html
    description_html_key
    raw_payload
    raw_payload_key
    structured_jd"]

    JE["job_embedding
    ---
    id PK
    job_id FK → job.id
    embedding_kind
    embedding_model
    embedding_dim
    embedding vector"]

    R["syncrun
    ---
    id PK
    source_id FK → sources.id
    source string (compat)
    started_at
    finished_at
    status
    fetched_count
    inserted_count
    updated_count
    closed_count"]

    S -->|source_id FK| J
    S -->|source_id FK| R
    J -->|job_id FK| JE
```

## 4. Target Database Direction

This is the shape implied by the roadmap, not the current implementation.

> **Note**: Location Modeling V1 explicitly defers canonical `LOCATION` and many-to-many `JOB_LOCATION` tables shown below. In V1, location modeling stops at extracting nullable, job-level structured fields directly on the `job` row (`city`, `region`, `country_code`, `workplace_type`).

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
        string source_key
        string external_job_id
        string title
        string apply_url
        string location_display_text
        string country_code
        string region
        string city
        boolean is_remote
        string status
        datetime published_at
    }

    JOB_CONTENT {
        uuid job_id PK
        string description_html_key
        string raw_payload_key
        jsonb structured_jd
    }

    JOB_EMBEDDING {
        uuid id PK
        uuid job_id FK
        string embedding_kind
        int embedding_target_revision
        string embedding_model
        int embedding_dim
        vector embedding
        datetime updated_at
    }

    SYNC_RUN {
        uuid id PK
        uuid source_id FK
        string source_key
        string status
        datetime started_at
        datetime finished_at
    }

    LOCATION {
        uuid id PK
        string display_name
        string country_code
        string region
        string city
        boolean is_remote
        string remote_scope
    }

    JOB_LOCATION {
        uuid job_id FK
        uuid location_id FK
        boolean is_primary
    }

    SOURCE ||--o{ JOB : owns
    SOURCE ||--o{ SYNC_RUN : tracks
    JOB ||--|| JOB_CONTENT : has
    JOB ||--o{ JOB_EMBEDDING : embeds
    JOB ||--o{ JOB_LOCATION : maps
    LOCATION ||--o{ JOB_LOCATION : maps
```

## 5. Matching / Retrieval Direction

Current matching works, but the retrieval strategy is still transitional.

The current baseline is close to:

- candidate profile -> one embedding
- job JD -> one embedding
- vector recall -> hard filters -> rerank

The likely target design is:

- structured filters first
- vector recall as an optional recall layer, not the only retrieval primitive
- embeddings stored in dedicated `job_embedding` table with active target resolution

```mermaid
flowchart LR
    U["Candidate profile"]
    UF["Hard filters<br/>work auth / degree / location / domain"]
    Q["Structured query representation<br/>title / skills / seniority / domain"]
    V["Optional vector recall"]
    C["Candidate job set"]
    R["Deterministic rerank"]
    L["Optional LLM rerank"]
    O["Top recommendations"]

    U --> Q
    U --> UF
    Q --> V
    UF --> C
    V --> C
    C --> R
    R --> L
    R --> O
    L --> O
```
