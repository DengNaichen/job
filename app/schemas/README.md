# Schemas

Pydantic models for API request/response data validation and serialization.

## Overview

Each model has three corresponding schemas:

- **Create** - Input data when creating a resource
- **Read** - Output data returned to client
- **Update** - Input data when updating a resource (all fields optional)

## Job Schemas

### JobCreate

Input when creating a job:

```python
{
    "source": "ashby",
    "external_job_id": "job_123",
    "title": "Senior Engineer",
    "apply_url": "https://example.com/apply",
    "normalized_apply_url": "https://example.com/apply",  # optional
    "status": "open",  # optional, default: open
    "location_hints": [  # optional normalized ingest hints
        {
            "source_raw": "San Francisco, CA",
            "city": "San Francisco",
            "region": "CA",
            "country_code": "US",
            "workplace_type": "onsite",
            "remote_scope": null
        }
    ],
    "department": "Engineering",  # optional
    "team": "Backend",  # optional
    "employment_type": "full-time",  # optional
    "content_fingerprint": "abc123",  # optional
    "dedupe_group_id": "group_1",  # optional
    "description_html": "<p>...</p>",  # optional
    "description_plain": "...",  # optional
    "published_at": "2024-01-01T00:00:00Z",  # optional
    "source_updated_at": "2024-01-01T00:00:00Z",  # optional
    "raw_payload": {}  # optional, default: {}
}
```

### JobRead

Job data returned to client:

```python
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "source": "ashby",
    "external_job_id": "job_123",
    "title": "Senior Engineer",
    "apply_url": "https://example.com/apply",
    "status": "open",
    "locations": [],  # normalized response location links
    "last_seen_at": "2024-01-01T00:00:00Z",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    ...
}
```

### JobUpdate

Input when updating a job (all fields optional):

```python
{
    "title": "Staff Engineer",  # optional
    "status": "closed",  # optional
    ...
}
```

---

## SyncRun Schemas

### SyncRunCreate

Input when creating a sync run:

```python
{
    "source": "ashby",
    "status": "running"  # optional, default: running
}
```

### SyncRunRead

Sync run data returned to client:

```python
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "source": "ashby",
    "status": "success",
    "started_at": "2024-01-01T00:00:00Z",
    "finished_at": "2024-01-01T00:05:00Z",
    "fetched_count": 100,
    "mapped_count": 95,
    "unique_count": 80,
    "deduped_by_external_id": 10,
    "deduped_by_apply_url": 5,
    "inserted_count": 20,
    "updated_count": 50,
    "closed_count": 10,
    "failed_count": 0,
    "error_summary": null,
    "created_at": "2024-01-01T00:00:00Z"
}
```

### SyncRunUpdate

Input when updating a sync run (all fields optional):

```python
{
    "status": "success",  # optional
    "finished_at": "2024-01-01T00:05:00Z",  # optional
    "fetched_count": 100,  # optional
    "inserted_count": 20,  # optional
    "error_summary": "Connection timeout",  # optional
    ...
}
```

---

## Design Principles

1. **Separation of Concerns** - Create/Read/Update separated, clarifying field requirements for each scenario
2. **Partial Updates** - All fields in Update schema are optional, supporting partial updates
3. **Type Safety** - Use Pydantic for data validation and type conversion
4. **from_attributes** - Read schema enables ORM model conversion
