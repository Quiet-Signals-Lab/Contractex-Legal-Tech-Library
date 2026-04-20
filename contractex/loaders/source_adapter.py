"""
Source adapter for URL and API-based document sources.

Extends the base DocumentLoader with network fetching, ETag-based change
detection, and exponential-backoff retry.  Two concrete subclasses cover
the most common patterns:

  - URLLoader  — arbitrary HTTP(S) URLs (HTML, PDF, plain text)
  - APILoader  — JSON REST APIs with auth headers and optional pagination

Both implement the standard ``DocumentLoader.load()`` interface so they are
drop-in replacements anywhere the existing loaders are accepted.
"""

from __future__ import annotations

import hashlib
import io
import logging
import time
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from contractex.exceptions import DocumentLoadError
from contractex.loaders.base import DocumentLoader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FetchCache:
    """Cached state from a previous fetch, used for change detection."""

    etag: str | None = None
    last_modified: str | None = None
    content_hash: str | None = None
    fetched_at: datetime | None = None


@dataclass
class FetchResult:
    """Result of a single remote fetch."""

    content: str
    content_type: str
    source_url: str
    etag: str | None = None
    last_modified: str | None = None
    content_hash: str = ""
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # False when server returned 304 Not Modified (content is empty string)
    changed: bool = True

    def to_cache(self) -> FetchCache:
        """Convert result to a FetchCache for the next request."""
        return FetchCache(
            etag=self.etag,
            last_modified=self.last_modified,
            content_hash=self.content_hash,
            fetched_at=self.fetched_at,
        )


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class SourceAdapter(DocumentLoader):
    """
    Abstract base for network-aware document loaders.

    Adds on top of ``DocumentLoader``:

    * ETag / Last-Modified change detection via ``changed_since()``
    * Exponential-backoff retry via ``_retry()``
    * Content hashing for deduplication

    Subclasses must implement ``fetch(source, cache)``.  The ``load()``
    method delegates to ``fetch()`` so the adapter is compatible with every
    place that accepts a ``DocumentLoader``.
    """

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
        user_agent: str = "contractex/0.1 (legal-tech-pipeline)",
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.user_agent = user_agent

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch(self, source: str, cache: FetchCache | None = None) -> FetchResult:
        """
        Fetch content from a remote source.

        Args:
            source: URL or API endpoint identifier.
            cache:  Optional prior cache state for conditional GET.

        Returns:
            FetchResult with content and headers.  If the server signals
            304 Not Modified, ``FetchResult.changed`` is False and
            ``FetchResult.content`` is an empty string.
        """
        ...

    # ------------------------------------------------------------------
    # DocumentLoader interface
    # ------------------------------------------------------------------

    def load(self, source: str) -> str:
        """Fetch the source and return its text content."""
        return self.fetch(source).content

    def load_with_metadata(self, source: str) -> dict[str, Any]:
        """Fetch with full provenance metadata."""
        result = self.fetch(source)
        return {
            "text": result.content,
            "metadata": {
                "source_url": result.source_url,
                "content_type": result.content_type,
                "content_hash": result.content_hash,
                "fetched_at": result.fetched_at.isoformat(),
                "etag": result.etag,
                "last_modified": result.last_modified,
                "changed": result.changed,
            },
        }

    # ------------------------------------------------------------------
    # Change detection helper
    # ------------------------------------------------------------------

    def changed_since(self, source: str, cache: FetchCache) -> bool:
        """
        Return True if the source has new content since *cache* was recorded.

        Prefers ETag / Last-Modified when available; falls back to content
        hash comparison.
        """
        return self.fetch(source, cache=cache).changed

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    def _retry(self, fn, *args, **kwargs):
        """Execute *fn* with exponential backoff.  Raises on final failure."""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                wait = self.backoff_factor**attempt
                logger.warning(
                    "Attempt %d/%d failed (%s); retrying in %.1fs",
                    attempt + 1,
                    self.max_retries,
                    exc,
                    wait,
                )
                time.sleep(wait)
        raise DocumentLoadError(f"All {self.max_retries} retry attempts failed") from last_exc

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# URLLoader
# ---------------------------------------------------------------------------


class URLLoader(SourceAdapter):
    """
    Load documents from arbitrary HTTP/HTTPS URLs.

    Supports:
    * HTML pages — stripped to readable plain text via stdlib html.parser
    * Plain text / JSON responses — returned as-is
    * PDF URLs — downloaded and parsed via PyMuPDF (requires pymupdf)
    * Conditional GET using ETag / Last-Modified headers

    Args:
        timeout:       HTTP request timeout in seconds.
        max_retries:   Number of retry attempts on transient errors.
        backoff_factor: Base for exponential backoff between retries.
        strip_html:    Convert HTML bodies to plain text (default True).
        headers:       Extra HTTP headers sent with every request.
    """

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
        strip_html: bool = True,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            timeout=timeout,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
        )
        self.strip_html = strip_html
        self.extra_headers = headers or {}

    def fetch(self, source: str, cache: FetchCache | None = None) -> FetchResult:
        """Fetch *source* URL with conditional-GET support."""
        try:
            import requests
        except ImportError as exc:
            raise DocumentLoadError(
                "requests is required for URLLoader. " "Install with: pip install requests"
            ) from exc

        req_headers: dict[str, str] = {
            "User-Agent": self.user_agent,
            **self.extra_headers,
        }
        if cache:
            if cache.etag:
                req_headers["If-None-Match"] = cache.etag
            elif cache.last_modified:
                req_headers["If-Modified-Since"] = cache.last_modified

        def _get():
            return requests.get(source, headers=req_headers, timeout=self.timeout)

        response = self._retry(_get)

        # 304 Not Modified — server confirmed nothing changed
        if response.status_code == 304:
            return FetchResult(
                content="",
                content_type=response.headers.get("Content-Type", ""),
                source_url=source,
                etag=cache.etag if cache else None,
                last_modified=cache.last_modified if cache else None,
                content_hash=(cache.content_hash or "") if cache else "",
                changed=False,
            )

        if not response.ok:
            raise DocumentLoadError(f"HTTP {response.status_code} fetching {source!r}")

        content_type = response.headers.get("Content-Type", "").lower()

        if "application/pdf" in content_type or source.lower().endswith(".pdf"):
            content = self._load_pdf_bytes(response.content, source)
        elif self.strip_html and ("text/html" in content_type or source.lower().endswith(".html")):
            content = self._strip_html(response.text)
        else:
            content = response.text

        content_hash = self._hash(content)
        changed = not (cache and cache.content_hash == content_hash)

        return FetchResult(
            content=content,
            content_type=content_type,
            source_url=source,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            content_hash=content_hash,
            changed=changed,
        )

    def supports(self, file_path: str) -> bool:
        parsed = urlparse(file_path)
        return parsed.scheme in ("http", "https")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_html(html: str) -> str:
        """Convert HTML to plain text, preserving paragraph breaks."""
        import re
        from html.parser import HTMLParser

        class _TextExtractor(HTMLParser):
            _SKIP = frozenset({"script", "style", "noscript", "head"})
            _BLOCK = frozenset({"p", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li"})

            def __init__(self) -> None:
                super().__init__()
                self._parts: list[str] = []
                self._skip_depth = 0

            def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
                if tag in self._SKIP:
                    self._skip_depth += 1
                if tag in self._BLOCK:
                    self._parts.append("\n")

            def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
                if tag in self._SKIP:
                    self._skip_depth = max(0, self._skip_depth - 1)

            def handle_data(self, data: str) -> None:  # type: ignore[override]
                if not self._skip_depth:
                    self._parts.append(data)

            def result(self) -> str:
                raw = "".join(self._parts)
                return re.sub(r"\n{3,}", "\n\n", raw).strip()

        extractor = _TextExtractor()
        extractor.feed(html)
        return extractor.result()

    @staticmethod
    def _load_pdf_bytes(data: bytes, source_url: str) -> str:
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise DocumentLoadError(
                "PyMuPDF is required to load PDF URLs. " "Install with: pip install pymupdf"
            ) from exc

        doc = fitz.open(stream=io.BytesIO(data), filetype="pdf")
        pages = [page.get_text("text") for page in doc]
        doc.close()
        return "\n\n".join(pages)


# ---------------------------------------------------------------------------
# APILoader
# ---------------------------------------------------------------------------


class APILoader(SourceAdapter):
    """
    Load documents from JSON REST APIs.

    Handles:
    * Bearer token / API key authentication via ``auth_header``
    * Fixed query parameters via ``params``
    * Text extraction from a dot-separated JSON field path (e.g. ``"data.opinion.text"``)
    * Pagination via RFC 5988 Link headers or common ``next`` / ``next_url`` keys

    Args:
        text_field:   Dot-separated path to the text value in the JSON response.
                      Defaults to ``"text"``.
        auth_header:  Full ``Authorization`` header value, e.g. ``"Token abc123"``.
        params:       Extra query parameters appended to every request.
        paginate:     Follow pagination (Link header or ``next`` key in JSON).
        max_pages:    Maximum pages to fetch (guard against runaway pagination).
        timeout:      HTTP request timeout in seconds.
        max_retries:  Number of retry attempts.
    """

    def __init__(
        self,
        text_field: str = "text",
        auth_header: str | None = None,
        params: dict[str, str] | None = None,
        paginate: bool = False,
        max_pages: int = 10,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
    ) -> None:
        super().__init__(
            timeout=timeout,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
        )
        self.text_field = text_field
        self.auth_header = auth_header
        self.base_params = params or {}
        self.paginate = paginate
        self.max_pages = max_pages

    def fetch(self, source: str, cache: FetchCache | None = None) -> FetchResult:
        """Fetch JSON API endpoint and extract text content."""
        try:
            import requests
        except ImportError as exc:
            raise DocumentLoadError(
                "requests is required for APILoader. " "Install with: pip install requests"
            ) from exc

        req_headers: dict[str, str] = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if self.auth_header:
            req_headers["Authorization"] = self.auth_header
        if cache and cache.etag:
            req_headers["If-None-Match"] = cache.etag

        def _get(url: str):
            return requests.get(
                url,
                headers=req_headers,
                params=self.base_params,
                timeout=self.timeout,
            )

        response = self._retry(_get, source)

        if response.status_code == 304:
            return FetchResult(
                content="",
                content_type="application/json",
                source_url=source,
                etag=cache.etag if cache else None,
                content_hash=(cache.content_hash or "") if cache else "",
                changed=False,
            )

        if not response.ok:
            raise DocumentLoadError(f"API returned HTTP {response.status_code} for {source!r}")

        data = response.json()
        page_texts = [self._extract_text(data)]

        if self.paginate:
            current_url = source
            for _ in range(self.max_pages - 1):
                next_url = self._next_link(response, data)
                if not next_url or next_url == current_url:
                    break
                response = self._retry(_get, next_url)
                if not response.ok:
                    logger.warning(
                        "Pagination stopped: HTTP %d from %r",
                        response.status_code,
                        next_url,
                    )
                    break
                data = response.json()
                page_texts.append(self._extract_text(data))
                current_url = next_url

        content = "\n\n".join(t for t in page_texts if t)
        content_hash = self._hash(content)
        changed = not (cache and cache.content_hash == content_hash)

        return FetchResult(
            content=content,
            content_type="application/json",
            source_url=source,
            etag=response.headers.get("ETag"),
            content_hash=content_hash,
            changed=changed,
        )

    def supports(self, file_path: str) -> bool:
        parsed = urlparse(file_path)
        return parsed.scheme in ("http", "https")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_text(self, data: Any) -> str:
        """Walk the dot-separated ``text_field`` path in *data*."""
        value: Any = data
        for key in self.text_field.split("."):
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return ""
            if value is None:
                return ""
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _next_link(response: Any, data: Any) -> str | None:
        """Extract the next-page URL from Link header or JSON body."""
        # RFC 5988: Link: <url>; rel="next"
        link_header: str = str(response.headers.get("Link", ""))
        if link_header:
            for part in link_header.split(","):
                part = part.strip()
                if 'rel="next"' in part or "rel='next'" in part:
                    url_part = part.split(";")[0].strip()
                    return url_part.strip("<>")

        # Common JSON pagination envelope keys
        if isinstance(data, dict):
            for key in ("next", "next_url", "nextPage", "next_cursor"):
                if val := data.get(key):
                    return str(val)

        return None
