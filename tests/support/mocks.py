from __future__ import annotations

from concurrent.futures import Future
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


class ExceptionAfterChunksStream:
    def __init__(self, chunks: Iterable[Any], error: Exception, on_close: Callable[[], None] | None = None):
        self._chunks = list(chunks)
        self._error = error
        self._on_close = on_close

    def __iter__(self):
        yield from self._chunks
        raise self._error

    def close(self):
        if callable(self._on_close):
            self._on_close()


class ImmediateExecutor:
    def __init__(self, max_workers: int, on_init: Callable[[int], None] | None = None):
        self.max_workers = int(max_workers)
        self._on_init = on_init
        if callable(self._on_init):
            self._on_init(self.max_workers)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def submit(self, fn, *args, **kwargs):
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:  # pragma: no cover - mirrors Future behavior
            future.set_exception(exc)
        return future


class ProxyAwareDDGSStub:
    attempts: list[Any] = []
    fail_on_proxy: bool = True
    text_results: list[dict[str, Any]] = []
    news_results: list[dict[str, Any]] = []

    def __init__(self, proxy=None):
        self.proxy = proxy

    def __enter__(self):
        type(self).attempts.append(self.proxy)
        if self.proxy and type(self).fail_on_proxy:
            raise RuntimeError("proxy failed")
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def text(self, query, max_results=5):
        del query, max_results
        return list(type(self).text_results)

    def news(self, query, region=None, safesearch=None, timelimit=None, max_results=5):
        del query, region, safesearch, timelimit, max_results
        return list(type(self).news_results)


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
