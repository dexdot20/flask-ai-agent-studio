from __future__ import annotations

import socket
from unittest.mock import Mock

import pytest

import web_tools


@pytest.mark.parametrize(
    ("url", "expected_reason"),
    [
        ("ftp://example.com/file.txt", "Only http and https are supported"),
        ("https:///missing-host", "Hostname not found"),
        ("http://localhost/internal", "Local addresses are prohibited"),
    ],
)
def test_is_safe_url_rejects_invalid_and_local_urls(url, expected_reason):
    safe, reason = web_tools._is_safe_url(url)

    assert safe is False
    assert reason == expected_reason


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "169.254.169.254"])
def test_validate_resolved_ip_address_rejects_non_public_ranges(address):
    with pytest.raises(socket.gaierror):
        web_tools._validate_resolved_ip_address(address)



def test_validate_resolved_ip_address_accepts_public_ip():
    web_tools._validate_resolved_ip_address("93.184.216.34")



def test_guarded_dns_resolution_restores_socket_after_error(monkeypatch):
    original = socket.getaddrinfo

    def sentinel_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", sentinel_getaddrinfo)

    with pytest.raises(RuntimeError, match="boom"):
        with web_tools._guarded_dns_resolution(enabled=True):
            assert socket.getaddrinfo is not sentinel_getaddrinfo
            raise RuntimeError("boom")

    assert socket.getaddrinfo is sentinel_getaddrinfo
    monkeypatch.setattr(socket, "getaddrinfo", original)



def test_fetch_url_tool_rejects_localhost_without_network_access():
    result = web_tools.fetch_url_tool("http://localhost/private")

    assert result["url"] == "http://localhost/private"
    assert result["content"] == ""
    assert result["error"] == "Local addresses are prohibited"



def test_search_web_tool_uses_cached_results_without_hitting_provider(monkeypatch):
    cached_rows = [{"title": "Cached", "url": "https://example.com", "snippet": "From cache"}]
    monkeypatch.setattr(web_tools, "cache_get", lambda key: cached_rows)
    monkeypatch.setattr(web_tools, "cache_set", lambda *args, **kwargs: None)

    monkeypatch.setattr(web_tools, "DDGS", Mock(side_effect=AssertionError("DDGS should not be created on cache hit")))

    results = web_tools.search_web_tool(["cached query"])

    assert results == cached_rows



def test_search_web_tool_deduplicates_urls_across_cached_queries(monkeypatch):
    cached_rows = iter([
        [
            {"title": "One", "url": "https://example.com/shared", "snippet": "A"},
            {"title": "Two", "url": "https://example.com/first", "snippet": "B"},
        ],
        [
            {"title": "Three", "url": "https://example.com/shared", "snippet": "C"},
            {"title": "Four", "url": "https://example.com/second", "snippet": "D"},
        ],
    ])

    def fake_cache_get(cache_key):
        assert cache_key.startswith("search:")
        return next(cached_rows)

    monkeypatch.setattr(web_tools, "cache_get", fake_cache_get)
    monkeypatch.setattr(web_tools, "cache_set", lambda *args, **kwargs: None)

    monkeypatch.setattr(web_tools, "DDGS", Mock(side_effect=AssertionError("DDGS should not run")))

    results = web_tools.search_web_tool(["first", "second"])

    assert [row["url"] for row in results] == [
        "https://example.com/shared",
        "https://example.com/first",
        "https://example.com/second",
    ]
