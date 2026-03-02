from __future__ import annotations

import asyncio
import cachetools
import httpx
from typing import Self
from urllib.parse import quote

from .client import BlobNotFoundError, BlobStorageError


class SupabaseBlobStorage:
    """Supabase Storage backend via the REST API."""

    def __init__(
        self,
        *,
        base_url: str,
        bucket: str,
        service_key: str,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.bucket = bucket
        self.service_key = service_key
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self._known_existing_keys = cachetools.TTLCache(maxsize=10000, ttl=3600)
        self.max_retries = 3
        # HTTP client is initialized lazily or via context manager
        self._client_instance: httpx.AsyncClient | None = None

    @property
    def is_enabled(self) -> bool:
        return True

    def _auth_headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self.service_key}",
            "apikey": self.service_key,
        }

    def _quoted_key(self, key: str) -> str:
        return quote(key.lstrip("/"), safe="/")

    def _info_url(self, key: str) -> str:
        return f"{self.base_url}/object/info/{self.bucket}/{self._quoted_key(key)}"

    def _upload_url(self, key: str) -> str:
        return f"{self.base_url}/object/{self.bucket}/{self._quoted_key(key)}"

    def _download_url(self, key: str) -> str:
        return f"{self.base_url}/object/authenticated/{self.bucket}/{self._quoted_key(key)}"

    def _client(self) -> httpx.AsyncClient:
        if self._client_instance is None:
            self._client_instance = httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            )
        return self._client_instance

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        if self._client_instance is not None:
            await self._client_instance.aclose()
            self._client_instance = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        content: bytes | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    content=content,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                await asyncio.sleep(0.5 * attempt)
                continue

            if response.status_code >= 500 and attempt < self.max_retries:
                await asyncio.sleep(0.5 * attempt)
                continue
            return response

        if last_error is not None:
            raise BlobStorageError(
                f"Supabase storage request failed for {url}: {last_error}"
            ) from last_error
        raise BlobStorageError(
            f"Supabase storage request failed for {url} after {self.max_retries} attempts"
        )

    @staticmethod
    def _is_missing_object_response(response: httpx.Response) -> bool:
        if response.status_code == 404:
            return True
        if response.status_code != 400:
            return False
        try:
            payload = response.json()
        except ValueError:
            return False
        error_value = str(payload.get("error") or "").strip().lower()
        message_value = str(payload.get("message") or "").strip().lower()
        return error_value == "not_found" and "object not found" in message_value

    async def upload_if_missing(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        content_encoding: str = "gzip",
    ) -> bool:
        if key in self._known_existing_keys:
            return False

        client = self._client()
        if True:
            info_response = await self._request_with_retry(
                client,
                "GET",
                self._info_url(key),
                headers=self._auth_headers(),
            )
            if info_response.status_code == 200:
                self._known_existing_keys[key] = True
                return False
            if not self._is_missing_object_response(info_response):
                raise BlobStorageError(
                    f"Supabase storage info lookup failed for {key}: "
                    f"{info_response.status_code} {info_response.text}"
                )

            upload_headers = {
                **self._auth_headers(),
                "content-type": content_type,
                "content-encoding": content_encoding,
                "x-upsert": "false",
            }
            upload_response = await self._request_with_retry(
                client,
                "POST",
                self._upload_url(key),
                headers=upload_headers,
                content=data,
            )
            if upload_response.status_code in {200, 201}:
                self._known_existing_keys[key] = True
                return True

            response_text = upload_response.text.lower()
            if upload_response.status_code in {400, 409} and "exist" in response_text:
                self._known_existing_keys[key] = True
                return False

            raise BlobStorageError(
                f"Supabase storage upload failed for {key}: "
                f"{upload_response.status_code} {upload_response.text}"
            )

    async def download(self, *, key: str) -> bytes:
        client = self._client()
        response = await self._request_with_retry(
            client,
            "GET",
            self._download_url(key),
            headers=self._auth_headers(),
        )
        if response.status_code == 404:
            raise BlobNotFoundError(f"Blob not found: {key}")
        if response.status_code != 200:
            raise BlobStorageError(
                f"Supabase storage download failed for {key}: "
                f"{response.status_code} {response.text}"
            )
        self._known_existing_keys[key] = True
        return response.content
