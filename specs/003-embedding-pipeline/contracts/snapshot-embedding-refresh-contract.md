# Contract: Snapshot-Triggered Embedding Refresh

## Scope

Defines behavior contract for embedding generation and refresh orchestration after successful full snapshot sync.

## 1. Trigger Contract

Input:
- One completed snapshot run with `status=success`
- Source boundary (`source_id`)
- Active embedding target (`kind/revision/model/dim`)

Guarantee:
- Refresh flow is triggered only from successful snapshot outcomes.
- Failed snapshot runs do not trigger refresh writes.

## 2. Selection Contract

Input:
- Source job state after reconciliation

Guarantee:
- Refresh considers jobs within snapshot-aligned source scope only.
- Closed jobs are excluded.
- Selection is deterministic for repeated runs over unchanged snapshot outcomes.

## 3. Generation Contract

Input:
- Selected job text payloads
- Embedding provider configuration

Guarantee:
- Transient provider failures retry within bounded limits.
- Non-transient errors fail fast.
- Unsupported dimensions follow deterministic fallback policy.
- Invalid provider payload shape/numeric values fail with explicit diagnostics.

## 4. Persistence Contract

Input:
- Generated vectors
- Active target identity

Guarantee:
- Writes are upserts under active-target uniqueness key.
- Repeated refresh runs do not create duplicate active-target rows.
- Refresh updates `updated_at` for successful writes.

## 5. Idempotency Contract

Given:
- Same successful snapshot outcome reprocessed multiple times

Guarantee:
- Final stored state is stable (no duplicate rows, deterministic target identity).

## 6. Error Handling Contract

- Provider errors propagate with actionable context.
- Partial failures are reported without corrupting target identity boundaries.
- Retry exhaustion is explicit and observable in execution result.

## Verification Targets

- Unit tests for client retry/fallback/validation behavior.
- Repository tests for active-target upsert idempotency.
- Sync/application tests for snapshot-triggered refresh orchestration semantics.
