"""
Source adapter for URL and API-based document sources.

Extends the base DocumentLoader with network fetching, ETag-based change
detection, and exponential-backoff retry.  Only http(s) URLs are fetched, and
credentials (auth header, extra headers) are never sent to a host other than
the one they were given for.  Two concrete subclasses cover
the most common patterns:

  - URLLoader  — arbitrary HTTP(S) URLs (HTML, PDF, plain text)
  - APILoader  — JSON REST APIs with auth headers and optional pagination

Both implement the standard ``DocumentLoader.load()`` interface so they are
drop-in replacements anywhere the existing loaders are accepted.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import socket
import time
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from contractex.__version__ import __version__
from contractex.exceptions import DocumentLoadError
from contractex.loaders.base import DocumentLoader

logger = logging.getLogger(__name__)

_REDIRECTS = (301, 302, 303, 307, 308)
_MAX_REDIRECTS = 5


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
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
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
        user_agent: str = f"contractex/{__version__} (legal-tech-pipeline)",
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

    def _retry(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Call *fn*, retrying connection errors and HTTP 429/5xx responses with
        exponential backoff.  Other errors (a malformed URL, say) are raised at
        once; the response of the last attempt is returned whatever its status.
        """
        import requests

        transient = (ConnectionError, TimeoutError, requests.ConnectionError, requests.Timeout)
        for attempt in range(self.max_retries):
            last = attempt == self.max_retries - 1
            try:
                response = fn(*args, **kwargs)
            except transient as exc:
                if last:
                    raise DocumentLoadError(
                        f"All {self.max_retries} retry attempts failed"
                    ) from exc
                reason = str(exc)
            except Exception as exc:
                raise DocumentLoadError(f"Request failed: {exc}") from exc
            else:
                if last or not (response.status_code == 429 or response.status_code >= 500):
                    return response
                reason = f"HTTP {response.status_code}"
            wait = self.backoff_factor**attempt
            logger.warning(
                "Attempt %d/%d failed (%s); retrying in %.1fs",
                attempt + 1,
                self.max_retries,
                reason,
                wait,
            )
            time.sleep(wait)
        raise DocumentLoadError(f"All {self.max_retries} retry attempts failed")

    def _get(
        self,
        url: str,
        headers: dict[str, str],
        credentialed: bool,
        params: dict[str, str] | None = None,
    ) -> Any:
        """
        GET *url* with retries, following redirects one hop at a time so each
        can be checked: with credentials only within the same host, and never
        from a public host to a private address.
        """
        import requests

        for _ in range(_MAX_REDIRECTS):
            if urlparse(url).scheme not in ("http", "https"):
                raise DocumentLoadError(f"Only http(s) URLs can be fetched, got {url!r}")
            response = self._retry(
                requests.get,
                url,
                headers=headers,
                params=params,
                timeout=self.timeout,
                allow_redirects=False,
            )
            if response.status_code not in _REDIRECTS:
                return response
            target = urljoin(url, response.headers.get("Location", ""))
            if credentialed and not _same_host(target, url):
                raise DocumentLoadError(
                    f"{url!r} redirects to another host ({target!r}); "
                    "not followed because the request carries credentials"
                )
            _refuse_public_to_private(url, target)
            url, params = target, None
        raise DocumentLoadError(f"Too many redirects fetching {url!r}")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()


def _same_host(url: str, other: str) -> bool:
    return urlparse(url).netloc.lower() == urlparse(other).netloc.lower()


def _is_private(url: str) -> bool:
    """
    True if *url*'s host is, or resolves to, an address that is not public.

    Raises ``OSError`` when the host does not resolve.
    """
    # The host must be read the way the HTTP client reads it: urllib and
    # urllib3 disagree on "http://a\\@b/", and the client connects to
    # urllib3's answer.
    from urllib3.util import parse_url

    host = (parse_url(url).host or "").strip("[]")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = [ipaddress.ip_address(a[4][0]) for a in socket.getaddrinfo(host, None)]
    return any(not a.is_global for a in addresses)


def _refuse_public_to_private(source: str, target: str) -> None:
    """
    Refuse to follow a link or redirect from a public host to a private one.

    A server on the internet must not be able to point the loader at
    loopback, a private network or a cloud metadata address and have the
    answer indexed as a document.  A source that is itself private (an
    intranet server you named) may link anywhere.  A target that cannot be
    checked is not followed.
    """
    if _same_host(source, target):
        return
    if "\\" in target or any(c.isspace() for c in target):
        raise DocumentLoadError(f"{source!r} points to a malformed URL ({target!r}); not followed")
    # shortcut: the name is resolved here and again by the HTTP client, so a
    # DNS answer that changes in between (rebinding) is not caught, and behind
    # an HTTP proxy the proxy resolves it; pin the resolved address if this
    # must hold against a hostile DNS server.
    try:
        if not _is_private(target):
            return
    except (OSError, ValueError) as exc:
        raise DocumentLoadError(
            f"{source!r} points to {target!r}, whose host could not be checked; not followed"
        ) from exc
    try:
        if _is_private(source):
            return
    except (OSError, ValueError):
        pass  # an unresolvable source is treated as public
    raise DocumentLoadError(f"{source!r} points to a private address ({target!r}); not followed")


# ---------------------------------------------------------------------------
# URLLoader
# ---------------------------------------------------------------------------


class URLLoader(SourceAdapter):
    """
    Load documents from arbitrary HTTP/HTTPS URLs.

    Supports:
    * HTML pages — stripped to readable plain text via stdlib html.parser
    * Plain text / JSON responses — returned as-is
    * PDF URLs — downloaded and parsed via pypdfium2
    * Conditional GET using ETag / Last-Modified headers

    Args:
        timeout:       HTTP request timeout in seconds.
        max_retries:   Number of retry attempts on transient errors.
        backoff_factor: Base for exponential backoff between retries.
        strip_html:    Convert HTML bodies to plain text (default True).
        headers:       Extra HTTP headers sent with every request.  They may
                       hold credentials, so with them a redirect to another
                       host is refused.
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
            import requests  # noqa: F401
        except ImportError as exc:
            raise DocumentLoadError(
                "requests is required for URLLoader. "
                "Install with: pip install 'contractex[network]'"
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

        response = self._get(source, req_headers, credentialed=bool(self.extra_headers))

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

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag in self._SKIP:
                    self._skip_depth += 1
                if tag in self._BLOCK:
                    self._parts.append("\n")

            def handle_endtag(self, tag: str) -> None:
                if tag in self._SKIP:
                    self._skip_depth = max(0, self._skip_depth - 1)

            def handle_data(self, data: str) -> None:
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
            import pypdfium2
        except ImportError as exc:
            raise DocumentLoadError(
                "pypdfium2 is required to load PDF URLs. Install with: pip install pypdfium2"
            ) from exc

        from contractex.loaders.pdf import pdf_text

        return pdf_text(pypdfium2.PdfDocument(data))


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
    * Pagination via RFC 5988 Link headers or common ``next`` / ``next_url`` keys.
      A relative link is resolved against the current page.  A link to another
      host is fetched without the auth header and query parameters; a page that
      fails raises ``DocumentLoadError`` rather than returning the pages so far.

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
            import requests  # noqa: F401
        except ImportError as exc:
            raise DocumentLoadError(
                "requests is required for APILoader. "
                "Install with: pip install 'contractex[network]'"
            ) from exc

        req_headers: dict[str, str] = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if self.auth_header:
            req_headers["Authorization"] = self.auth_header
        if cache and cache.etag:
            req_headers["If-None-Match"] = cache.etag

        credentialed = bool(self.auth_header)
        response = self._get(source, req_headers, credentialed, self.base_params)

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
            public_headers = {k: v for k, v in req_headers.items() if k != "Authorization"}
            for _ in range(self.max_pages - 1):
                link = self._next_link(response, data)
                if not link:
                    break
                if not link.startswith(("http://", "https://", "/", "?")):
                    raise DocumentLoadError(
                        f"Cannot follow pagination value {link!r} from {current_url!r}: "
                        "not a URL"
                    )
                next_url = urljoin(current_url, link)
                if next_url == current_url:
                    break
                if _same_host(next_url, source):
                    response = self._get(next_url, req_headers, credentialed, self.base_params)
                else:
                    _refuse_public_to_private(source, next_url)
                    response = self._get(next_url, public_headers, credentialed=False)
                if not response.ok:
                    raise DocumentLoadError(
                        f"API returned HTTP {response.status_code} for {next_url!r}"
                    )
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
