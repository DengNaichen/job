# Fetchers

负责从各招聘平台 API 获取原始职位数据的模块。

## 架构设计

### BaseFetcher

所有 fetcher 继承自 `BaseFetcher`，提供：

- **抽象方法**：
  - `source_name` - 数据源标识符
  - `fetch(slug, **kwargs)` - 获取原始职位数据

- **HTTP 重试机制**：
  - `request_with_retry()` - 带重试的 HTTP 请求
  - `request_json_with_retry()` - 带重试的 JSON 请求
  - `request_with_graceful_retry()` - 优雅失败模式（返回 None 而非抛异常）

- **并发详情获取**：
  - `fetch_details_concurrently()` - 并发获取职位详情

### RetryConfig

```python
@dataclass
class RetryConfig:
    max_retries: int = 3
    retryable_status_codes: set[int] = {429, 500, 502, 503, 504}
    backoff_base_seconds: float = 0.25
    exponential_backoff: bool = True
```

## 已支持的数据源

| Fetcher | 数据源 | 说明 |
|---------|--------|------|
| `GreenhouseFetcher` | Greenhouse | ATS 平台 |
| `LeverFetcher` | Lever | ATS 平台 |
| `AshbyFetcher` | Ashby | ATS 平台 |
| `SmartRecruitersFetcher` | SmartRecruiters | ATS 平台 |
| `EightfoldFetcher` | Eightfold | AI 招聘平台 |
| `AppleFetcher` | Apple | 自建招聘系统 |
| `UberFetcher` | Uber | 自建招聘系统 |
| `TikTokFetcher` | TikTok | 自建招聘系统 |

## 添加新的 Fetcher

```python
from typing import Any
import httpx
from app.ingest.fetchers.base import BaseFetcher


class NewPlatformFetcher(BaseFetcher):
    """NewPlatform API fetcher."""

    BASE_URL = "https://api.newplatform.com"

    @property
    def source_name(self) -> str:
        return "newplatform"

    async def fetch(self, slug: str, **kwargs) -> list[dict[str, Any]]:
        """
        Fetch job data from NewPlatform.

        Args:
            slug: Company identifier
        """
        url = f"{self.BASE_URL}/{slug}/jobs"

        async with httpx.AsyncClient() as client:
            # 使用带重试的请求方法
            data = await self.request_json_with_retry(
                client, method="GET", url=url
            )

        return data.get("jobs", [])
```

## 使用示例

```python
from app.ingest.fetchers import GreenhouseFetcher

fetcher = GreenhouseFetcher()
jobs = await fetcher.fetch("airbnb")
```

## 测试

```bash
pytest tests/unit/ingest/fetchers/
```
