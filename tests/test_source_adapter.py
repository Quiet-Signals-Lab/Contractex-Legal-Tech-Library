"""
Unit tests for SourceAdapter, URLLoader, and APILoader.

All HTTP calls are mocked — no real network traffic.
"""

from unittest.mock import MagicMock, patch

import pytest

from contractex.exceptions import DocumentLoadError
from contractex.loaders.source_adapter import (
    APILoader,
    FetchCache,
    FetchResult,
    URLLoader,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(
    status_code: int = 200,
    text: str = "document text",
    content_type: str = "text/plain",
    headers: dict | None = None,
    json_data: dict | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.text = text
    resp.content = text.encode()
    resp.headers = {
        "Content-Type": content_type,
        **(headers or {}),
    }
    resp.json.return_value = json_data or {}
    return resp


# ---------------------------------------------------------------------------
# FetchCache / FetchResult
# ---------------------------------------------------------------------------


class TestFetchCache:
    def test_defaults_are_none(self):
        cache = FetchCache()
        assert cache.etag is None
        assert cache.content_hash is None

    def test_to_cache_from_result(self):
        result = FetchResult(
            content="text",
            content_type="text/plain",
            source_url="https://example.com",
            etag='"abc123"',
            content_hash="deadbeef",
        )
        cache = result.to_cache()
        assert cache.etag == '"abc123"'
        assert cache.content_hash == "deadbeef"


# ---------------------------------------------------------------------------
# URLLoader — successful fetches
# ---------------------------------------------------------------------------


class TestURLLoaderFetch:
    @patch("requests.get")
    def test_plain_text_fetch(self, mock_get):
        mock_get.return_value = _mock_response(text="plain text content")
        loader = URLLoader()
        result = loader.fetch("https://example.com/doc.txt")
        assert result.content == "plain text content"
        assert result.source_url == "https://example.com/doc.txt"
        assert result.changed is True

    @patch("requests.get")
    def test_load_interface(self, mock_get):
        mock_get.return_value = _mock_response(text="hello")
        loader = URLLoader()
        text = loader.load("https://example.com/")
        assert text == "hello"

    @patch("requests.get")
    def test_load_with_metadata_includes_provenance(self, mock_get):
        mock_get.return_value = _mock_response(
            text="content",
            headers={"ETag": '"etag1"'},
        )
        loader = URLLoader()
        result = loader.load_with_metadata("https://example.com/")
        assert result["text"] == "content"
        assert result["metadata"]["etag"] == '"etag1"'
        assert result["metadata"]["source_url"] == "https://example.com/"

    @patch("requests.get")
    def test_etag_sent_when_cache_provided(self, mock_get):
        mock_get.return_value = _mock_response(text="fresh content")
        cache = FetchCache(etag='"old-etag"')
        loader = URLLoader()
        loader.fetch("https://example.com/", cache=cache)
        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs["headers"]["If-None-Match"] == '"old-etag"'

    @patch("requests.get")
    def test_last_modified_sent_when_etag_absent(self, mock_get):
        mock_get.return_value = _mock_response(text="fresh")
        cache = FetchCache(last_modified="Tue, 01 Jan 2024 00:00:00 GMT")
        loader = URLLoader()
        loader.fetch("https://example.com/", cache=cache)
        call_kwargs = mock_get.call_args.kwargs
        assert "If-Modified-Since" in call_kwargs["headers"]

    @patch("requests.get")
    def test_304_returns_unchanged_result(self, mock_get):
        mock_get.return_value = _mock_response(status_code=304, text="")
        mock_get.return_value.ok = False  # 304 is not in 2xx
        cache = FetchCache(etag='"abc"', content_hash="old-hash")
        loader = URLLoader()
        result = loader.fetch("https://example.com/", cache=cache)
        assert result.changed is False
        assert result.content == ""
        assert result.etag == '"abc"'

    @patch("requests.get")
    def test_content_hash_unchanged_detection(self, mock_get):
        from contractex.loaders.source_adapter import SourceAdapter

        text = "same content"
        content_hash = SourceAdapter._hash(text)
        mock_get.return_value = _mock_response(text=text)
        cache = FetchCache(content_hash=content_hash)
        loader = URLLoader()
        result = loader.fetch("https://example.com/", cache=cache)
        assert result.changed is False

    @patch("requests.get")
    def test_http_error_raises_document_load_error(self, mock_get):
        mock_get.return_value = _mock_response(status_code=404)
        loader = URLLoader(max_retries=1)
        with pytest.raises(DocumentLoadError, match="HTTP 404"):
            loader.fetch("https://example.com/missing")

    @patch("requests.get")
    def test_extra_headers_sent(self, mock_get):
        mock_get.return_value = _mock_response(text="ok")
        loader = URLLoader(headers={"X-Custom": "value"})
        loader.fetch("https://example.com/")
        call_headers = mock_get.call_args.kwargs["headers"]
        assert call_headers["X-Custom"] == "value"

    @patch("requests.get")
    def test_retry_on_transient_error(self, mock_get):
        mock_get.side_effect = [
            ConnectionError("transient"),
            _mock_response(text="ok after retry"),
        ]
        loader = URLLoader(max_retries=3, backoff_factor=0.01)
        result = loader.fetch("https://example.com/")
        assert result.content == "ok after retry"

    @patch("requests.get")
    def test_exhausted_retries_raise(self, mock_get):
        mock_get.side_effect = ConnectionError("persistent failure")
        loader = URLLoader(max_retries=2, backoff_factor=0.01)
        with pytest.raises(DocumentLoadError, match="retry"):
            loader.fetch("https://example.com/")

    def test_supports_http_https(self):
        loader = URLLoader()
        assert loader.supports("https://example.com/doc.pdf") is True
        assert loader.supports("http://example.com/") is True
        assert loader.supports("/local/file.pdf") is False


# ---------------------------------------------------------------------------
# URLLoader — HTML stripping
# ---------------------------------------------------------------------------


class TestURLLoaderHTMLStrip:
    @patch("requests.get")
    def test_html_stripped_to_text(self, mock_get):
        html = "<html><head><title>T</title></head><body><p>Hello world</p></body></html>"
        mock_get.return_value = _mock_response(
            text=html,
            content_type="text/html",
        )
        loader = URLLoader(strip_html=True)
        result = loader.fetch("https://example.com/page.html")
        assert "Hello world" in result.content
        assert "<p>" not in result.content
        assert "<html>" not in result.content

    @patch("requests.get")
    def test_script_tags_removed(self, mock_get):
        html = "<html><body><script>alert('xss')</script><p>Real content</p></body></html>"
        mock_get.return_value = _mock_response(text=html, content_type="text/html")
        loader = URLLoader(strip_html=True)
        result = loader.fetch("https://example.com/")
        assert "alert" not in result.content
        assert "Real content" in result.content

    @patch("requests.get")
    def test_strip_html_false_preserves_html(self, mock_get):
        html = "<p>Hello</p>"
        mock_get.return_value = _mock_response(text=html, content_type="text/html")
        loader = URLLoader(strip_html=False)
        result = loader.fetch("https://example.com/")
        assert "<p>" in result.content


# ---------------------------------------------------------------------------
# APILoader — successful fetches
# ---------------------------------------------------------------------------


class TestAPILoaderFetch:
    @patch("requests.get")
    def test_simple_json_text_field(self, mock_get):
        mock_get.return_value = _mock_response(
            content_type="application/json",
            json_data={"text": "the opinion text"},
        )
        loader = APILoader(text_field="text")
        result = loader.fetch("https://api.example.com/opinions/1")
        assert result.content == "the opinion text"

    @patch("requests.get")
    def test_nested_text_field(self, mock_get):
        mock_get.return_value = _mock_response(
            content_type="application/json",
            json_data={"data": {"opinion": {"text": "nested content"}}},
        )
        loader = APILoader(text_field="data.opinion.text")
        result = loader.fetch("https://api.example.com/")
        assert result.content == "nested content"

    @patch("requests.get")
    def test_missing_text_field_returns_empty(self, mock_get):
        mock_get.return_value = _mock_response(
            content_type="application/json",
            json_data={"other_key": "value"},
        )
        loader = APILoader(text_field="text")
        result = loader.fetch("https://api.example.com/")
        assert result.content == ""

    @patch("requests.get")
    def test_auth_header_sent(self, mock_get):
        mock_get.return_value = _mock_response(
            content_type="application/json",
            json_data={"text": "ok"},
        )
        loader = APILoader(auth_header="Token secret-key")
        loader.fetch("https://api.example.com/")
        call_headers = mock_get.call_args.kwargs["headers"]
        assert call_headers["Authorization"] == "Token secret-key"

    @patch("requests.get")
    def test_base_params_sent(self, mock_get):
        mock_get.return_value = _mock_response(
            content_type="application/json",
            json_data={"text": "ok"},
        )
        loader = APILoader(params={"format": "json", "jurisdiction": "us"})
        loader.fetch("https://api.example.com/")
        call_params = mock_get.call_args.kwargs["params"]
        assert call_params["jurisdiction"] == "us"

    @patch("requests.get")
    def test_304_not_modified(self, mock_get):
        mock_get.return_value = _mock_response(status_code=304, text="")
        mock_get.return_value.ok = False
        cache = FetchCache(etag='"abc"', content_hash="hash")
        loader = APILoader()
        result = loader.fetch("https://api.example.com/", cache=cache)
        assert result.changed is False

    @patch("requests.get")
    def test_api_error_raises(self, mock_get):
        mock_get.return_value = _mock_response(status_code=401)
        loader = APILoader(max_retries=1)
        with pytest.raises(DocumentLoadError, match="HTTP 401"):
            loader.fetch("https://api.example.com/")

    def test_supports_http_https(self):
        loader = APILoader()
        assert loader.supports("https://api.example.com/") is True
        assert loader.supports("/local/path") is False


# ---------------------------------------------------------------------------
# APILoader — pagination
# ---------------------------------------------------------------------------


class TestAPILoaderPagination:
    @patch("requests.get")
    def test_link_header_pagination(self, mock_get):
        page1 = _mock_response(
            content_type="application/json",
            json_data={"text": "page 1 content"},
            headers={"Link": '<https://api.example.com/page2>; rel="next"'},
        )
        page2 = _mock_response(
            content_type="application/json",
            json_data={"text": "page 2 content"},
        )
        mock_get.side_effect = [page1, page2]

        loader = APILoader(text_field="text", paginate=True, max_pages=5)
        result = loader.fetch("https://api.example.com/page1")
        assert "page 1 content" in result.content
        assert "page 2 content" in result.content

    @patch("requests.get")
    def test_json_next_key_pagination(self, mock_get):
        page1 = _mock_response(
            content_type="application/json",
            json_data={"text": "first", "next": "https://api.example.com/page2"},
        )
        page2 = _mock_response(
            content_type="application/json",
            json_data={"text": "second"},
        )
        mock_get.side_effect = [page1, page2]

        loader = APILoader(text_field="text", paginate=True, max_pages=5)
        result = loader.fetch("https://api.example.com/page1")
        assert "first" in result.content
        assert "second" in result.content

    @patch("requests.get")
    def test_max_pages_respected(self, mock_get):
        # Each page's "next" points to the subsequent URL so they are distinct
        def _page(i):
            return _mock_response(
                content_type="application/json",
                json_data={"text": f"content {i}", "next": f"https://api.example.com/page{i+1}"},
            )

        mock_get.side_effect = [_page(i) for i in range(10)]
        loader = APILoader(text_field="text", paginate=True, max_pages=3)
        # Start at page0 so the first "next" (page1) is a different URL
        result = loader.fetch("https://api.example.com/page0")
        # Should have fetched exactly max_pages pages
        assert mock_get.call_count == 3
        assert "content 0" in result.content

    @patch("requests.get")
    def test_no_pagination_when_disabled(self, mock_get):
        page1 = _mock_response(
            content_type="application/json",
            json_data={"text": "page 1", "next": "https://api.example.com/page2"},
        )
        mock_get.return_value = page1
        loader = APILoader(text_field="text", paginate=False)
        loader.fetch("https://api.example.com/page1")
        assert mock_get.call_count == 1


# ---------------------------------------------------------------------------
# SourceAdapter.changed_since
# ---------------------------------------------------------------------------


class TestChangedSince:
    @patch("requests.get")
    def test_changed_since_true_when_content_differs(self, mock_get):
        mock_get.return_value = _mock_response(text="new content")
        from contractex.loaders.source_adapter import SourceAdapter

        cache = FetchCache(content_hash=SourceAdapter._hash("old content"))
        loader = URLLoader()
        assert loader.changed_since("https://example.com/", cache=cache) is True

    @patch("requests.get")
    def test_changed_since_false_when_same(self, mock_get):
        from contractex.loaders.source_adapter import SourceAdapter

        text = "same content"
        mock_get.return_value = _mock_response(text=text)
        cache = FetchCache(content_hash=SourceAdapter._hash(text))
        loader = URLLoader()
        assert loader.changed_since("https://example.com/", cache=cache) is False
