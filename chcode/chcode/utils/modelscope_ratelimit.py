"""ModelScope API 调用次数监控（解耦模块）

通过自定义 httpx Transport 捕获响应头中的 ratelimit 信息，
供状态栏实时显示。仅在 base_url 包含 modelscope 时启用。
"""

from __future__ import annotations

import httpx
import threading

_ratelimit_data: dict = {}
_ratelimit_lock = threading.Lock()

_cached_sync: httpx.Client | None = None
_cached_async: httpx.AsyncClient | None = None
_client_lock = threading.Lock()


def get_ratelimit() -> dict:
    with _ratelimit_lock:
        return dict(_ratelimit_data) if _ratelimit_data else {}


def is_modelscope_model(model_config: dict) -> bool:
    return "modelscope" in model_config.get("base_url", "").lower()


def _update_ratelimit(headers: httpx.Headers) -> None:
    total_limit = headers.get("modelscope-ratelimit-requests-limit")
    if not total_limit:
        return
    try:
        with _ratelimit_lock:
            _ratelimit_data.update({
                "total_limit": int(total_limit),
                "total_remaining": int(headers.get("modelscope-ratelimit-requests-remaining", 0)),
                "model_limit": int(headers.get("modelscope-ratelimit-model-requests-limit", 0)),
                "model_remaining": int(headers.get("modelscope-ratelimit-model-requests-remaining", 0)),
            })
    except (ValueError, TypeError):
        pass


class _HeaderCaptureTransport(httpx.HTTPTransport):
    def handle_request(self, request):
        response = super().handle_request(request)
        _update_ratelimit(response.headers)
        return response


class _HeaderCaptureAsyncTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        response = await super().handle_async_request(request)
        _update_ratelimit(response.headers)
        return response


def get_modelscope_clients() -> tuple[httpx.Client, httpx.AsyncClient]:
    global _cached_sync, _cached_async
    with _client_lock:
        if _cached_sync is None or _cached_async is None:
            _cached_sync = httpx.Client(transport=_HeaderCaptureTransport())
            _cached_async = httpx.AsyncClient(transport=_HeaderCaptureAsyncTransport())
        return _cached_sync, _cached_async
