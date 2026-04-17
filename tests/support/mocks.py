from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable, Iterable


class CallbackHttpClient:
    def __init__(self, *args, **kwargs):
        self.proxy = kwargs.get("proxy")
        self.trust_env = kwargs.get("trust_env")
        self._on_close: Callable[[], None] | None = kwargs.get("on_close")

    def close(self):
        if callable(self._on_close):
            self._on_close()


class CallbackOpenAI:
    def __init__(self, **kwargs):
        self.http_client = kwargs.get("http_client")
        self._on_create: Callable[..., Any] | None = kwargs.get("on_create")
        self._on_close: Callable[[], None] | None = kwargs.get("on_close")
        self.chat = SimpleNamespace(completions=self)

    def create(self, *args, **kwargs):
        if callable(self._on_create):
            return self._on_create(*args, **kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    def close(self):
        if callable(self._on_close):
            self._on_close()


class StaticStream:
    def __init__(self, chunks: Iterable[Any], on_close: Callable[[], None] | None = None):
        self._chunks = list(chunks)
        self._on_close = on_close

    def __iter__(self):
        yield from self._chunks

    def close(self):
        if callable(self._on_close):
            self._on_close()


class SimpleRequestsResponse:
    def __init__(
        self,
        *,
        url: str,
        status_code: int = 200,
        content_type: str = "text/plain; charset=utf-8",
        chunks: Iterable[bytes] | None = None,
    ):
        self.headers = {"Content-Type": content_type}
        self.url = url
        self.encoding = "utf-8"
        self.status_code = status_code
        self._chunks = list(chunks or [])

    def iter_content(self, chunk_size=8192):
        del chunk_size
        yield from self._chunks

    def raise_for_status(self):
        return None


class SimpleRequestsSession:
    def __init__(self, get_handler: Callable[..., Any]):
        self.max_redirects = 0
        self.trust_env = False
        self.proxies: dict[str, str] = {}
        self._get_handler = get_handler

    def get(self, *args, **kwargs):
        return self._get_handler(*args, **kwargs)

    def close(self):
        return None


class SimplePDF:
    def __init__(self, pages: list[Any]):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class SimpleCrop:
    def __init__(self, text: str = ""):
        self._text = text

    def extract_text(self, **kwargs):
        del kwargs
        return self._text
