# LLM Usage Tracking Notes

## What Changed
- Token accounting is now request-scoped for async LLM workflows.
- `app.services.infra.llm.client.complete_json(...)` records usage through a single path.
- Callback-based accounting was removed to avoid duplicate token counts.

## API Surface
- Stable public API remains:
  - `from app.services.infra.llm import complete_json, get_llm_config, get_token_usage`
- Internal scoped helpers live in:
  - `app.services.infra.llm.usage.start_usage_scope()`
  - `app.services.infra.llm.usage.snapshot_usage()`

## Migration Guidance
- Existing scripts that call `get_token_usage().reset()` continue to work.
- For concurrent request windows, prefer a scoped pattern:

```python
from app.services.infra.llm.usage import snapshot_usage, start_usage_scope

with start_usage_scope():
    # run one logical request window (possibly concurrent tasks)
    ...
    usage_summary = snapshot_usage()
```

- Avoid resetting global counters from shared service paths.
