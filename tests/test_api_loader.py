"""URLLoader / APILoader: credentials, pagination, retries and URL schemes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests

from contractex import __version__
from contractex.exceptions import DocumentLoadError
from contractex.loaders.source_adapter import APILoader, URLLoader
from tests.test_source_adapter import _mock_response


def _json(data: dict, status_code: int = 200, headers: dict | None = None):
    return _mock_response(
        status_code=status_code,
        content_type="application/json",
        json_data=data,
        headers=headers,
    )


# Name → address for the hosts these tests use; nothing here touches real DNS.
HOSTS = {"internal.attacker.test": "127.0.0.1", "metadata.attacker.test": "169.254.169.254"}


@pytest.fixture(autouse=True)
def fake_dns():
    def getaddrinfo(host, *args, **kwargs):
        return [(None, None, None, "", (HOSTS.get(host, "93.184.216.34"), 0))]

    with patch("socket.getaddrinfo", getaddrinfo):
        yield


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("contractex.loaders.source_adapter.time.sleep") as sleep:
        yield sleep


class TestPagination:
    @patch("requests.get")
    def test_auth_and_params_are_not_sent_to_another_host(self, mock_get):
        mock_get.side_effect = [
            _json({"text": "page 1", "next": "https://attacker.test/collect?page=2"}),
            _json({"text": "page 2"}),
        ]
        loader = APILoader(auth_header="Token SECRET", params={"api_key": "K"}, paginate=True)
        loader.fetch("https://api.court.test/v1/opinions")

        first, second = mock_get.call_args_list
        assert first.kwargs["headers"]["Authorization"] == "Token SECRET"
        assert first.kwargs["params"] == {"api_key": "K"}
        assert second.args[0] == "https://attacker.test/collect?page=2"
        assert "Authorization" not in second.kwargs["headers"]
        assert not second.kwargs.get("params")

    @patch("requests.get")
    def test_auth_is_kept_for_the_same_host(self, mock_get):
        mock_get.side_effect = [
            _json({"text": "page 1", "next": "https://api.court.test/v1/opinions?page=2"}),
            _json({"text": "page 2"}),
        ]
        APILoader(auth_header="Token SECRET", paginate=True).fetch("https://api.court.test/v1/")
        assert mock_get.call_args_list[1].kwargs["headers"]["Authorization"] == "Token SECRET"

    @pytest.mark.parametrize(
        ("link", "expected"),
        [
            ("/v1/opinions?page=2", "https://api.court.test/v1/opinions?page=2"),
            ("?page=2", "https://api.court.test/v1/opinions?page=2"),
        ],
    )
    @patch("requests.get")
    def test_relative_next_link_is_resolved(self, mock_get, link, expected):
        mock_get.side_effect = [_json({"text": "page 1", "next": link}), _json({"text": "page 2"})]
        result = APILoader(paginate=True).fetch("https://api.court.test/v1/opinions")
        assert mock_get.call_args_list[1].args[0] == expected
        assert result.content == "page 1\n\npage 2"

    @patch("requests.get")
    def test_failed_page_raises_instead_of_returning_truncated_content(self, mock_get):
        mock_get.side_effect = [
            _json({"text": "page 1", "next": "https://api.court.test/v1?page=2"}),
            _json({}, status_code=404),
        ]
        with pytest.raises(DocumentLoadError, match="HTTP 404.*page=2"):
            APILoader(paginate=True).fetch("https://api.court.test/v1")

    @patch("requests.get")
    def test_cursor_that_is_not_a_link_raises(self, mock_get):
        mock_get.return_value = _json({"text": "page 1", "next_cursor": "eyJjdXJzb3IiOjJ9"})
        with pytest.raises(DocumentLoadError, match="eyJjdXJzb3IiOjJ9"):
            APILoader(paginate=True).fetch("https://api.court.test/v1")
        assert mock_get.call_count == 1


class TestRetries:
    @patch("requests.get")
    def test_503_is_retried(self, mock_get, no_sleep):
        mock_get.side_effect = [_mock_response(status_code=503), _mock_response(text="ok")]
        assert URLLoader().fetch("https://docs.test/a.txt").content == "ok"
        assert no_sleep.call_count == 1

    @patch("requests.get")
    def test_429_is_retried_then_reported(self, mock_get, no_sleep):
        mock_get.return_value = _mock_response(status_code=429)
        with pytest.raises(DocumentLoadError, match="HTTP 429"):
            URLLoader(max_retries=3).fetch("https://docs.test/a.txt")
        assert mock_get.call_count == 3
        assert no_sleep.call_count == 2  # no sleep after the last attempt

    @patch("requests.get")
    def test_404_is_not_retried(self, mock_get, no_sleep):
        mock_get.return_value = _mock_response(status_code=404)
        with pytest.raises(DocumentLoadError, match="HTTP 404"):
            URLLoader().fetch("https://docs.test/missing")
        assert mock_get.call_count == 1
        assert no_sleep.call_count == 0

    @patch("requests.get")
    def test_connection_errors_are_retried_without_a_final_sleep(self, mock_get, no_sleep):
        mock_get.side_effect = requests.ConnectionError("refused")
        with pytest.raises(DocumentLoadError, match="retry"):
            URLLoader(max_retries=3).fetch("https://docs.test/a.txt")
        assert mock_get.call_count == 3
        assert no_sleep.call_count == 2

    @patch("requests.get")
    def test_permanent_request_error_is_not_retried(self, mock_get, no_sleep):
        mock_get.side_effect = requests.exceptions.InvalidURL("bad url")
        with pytest.raises(DocumentLoadError, match="bad url"):
            URLLoader().fetch("https://docs.test/a.txt")
        assert mock_get.call_count == 1
        assert no_sleep.call_count == 0


class TestSchemes:
    @pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://docs.test/a.txt", "not a url"])
    @pytest.mark.parametrize("loader", [URLLoader(), APILoader()])
    @patch("requests.get")
    def test_only_http_and_https_are_fetched(self, mock_get, loader, url):
        with pytest.raises(DocumentLoadError, match="http"):
            loader.fetch(url)
        mock_get.assert_not_called()


class TestRedirectsWithCredentials:
    @pytest.mark.parametrize(
        "loader", [APILoader(auth_header="Token SECRET"), URLLoader(headers={"X-API-Key": "K"})]
    )
    @patch("requests.get")
    def test_redirect_to_another_host_is_refused(self, mock_get, loader):
        mock_get.return_value = _mock_response(
            status_code=302, headers={"Location": "https://attacker.test/collect"}
        )
        with pytest.raises(DocumentLoadError, match="attacker.test"):
            loader.fetch("https://api.court.test/v1")
        assert mock_get.call_count == 1
        assert mock_get.call_args.kwargs["allow_redirects"] is False

    @patch("requests.get")
    def test_redirect_on_the_same_host_is_followed(self, mock_get):
        mock_get.side_effect = [
            _mock_response(status_code=301, headers={"Location": "/v1/"}),
            _json({"text": "page 1"}),
        ]
        result = APILoader(auth_header="Token SECRET").fetch("https://api.court.test/v1")
        assert result.content == "page 1"
        assert mock_get.call_args_list[1].args[0] == "https://api.court.test/v1/"


class TestRedirectsToPrivateAddresses:
    """A public server must not be able to point the loader at an internal host."""

    @pytest.mark.parametrize(
        "location",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1:8080/admin",
            "http://10.0.0.5/internal.txt",
            "http://[::1]/",
            "https://internal.attacker.test/",
            "https://metadata.attacker.test/",
        ],
    )
    @patch("requests.get")
    def test_redirect_from_public_host_to_private_address_is_refused(self, mock_get, location):
        mock_get.side_effect = [
            _mock_response(status_code=302, headers={"Location": location}),
            _mock_response(text="AWS_SECRET=internal-only"),
        ]
        with pytest.raises(DocumentLoadError, match="private"):
            URLLoader().fetch("https://docs.test/a.txt")
        assert mock_get.call_count == 1

    @patch("requests.get")
    def test_redirect_between_public_hosts_is_followed(self, mock_get):
        mock_get.side_effect = [
            _mock_response(status_code=302, headers={"Location": "https://cdn.docs.test/a.txt"}),
            _mock_response(text="public text"),
        ]
        assert URLLoader().fetch("https://docs.test/a.txt").content == "public text"
        assert mock_get.call_args_list[1].args[0] == "https://cdn.docs.test/a.txt"
        assert all(c.kwargs["allow_redirects"] is False for c in mock_get.call_args_list)

    @patch("requests.get")
    def test_redirect_inside_a_private_network_is_followed(self, mock_get):
        mock_get.side_effect = [
            _mock_response(status_code=302, headers={"Location": "http://10.0.0.6/a.txt"}),
            _mock_response(text="intranet text"),
        ]
        assert URLLoader().fetch("http://10.0.0.5/a.txt").content == "intranet text"

    @patch("requests.get")
    def test_pagination_link_from_public_api_to_private_address_is_refused(self, mock_get):
        mock_get.side_effect = [
            _json({"text": "page 1", "next": "http://169.254.169.254/latest/meta-data/"}),
            _json({"text": "secret"}),
        ]
        with pytest.raises(DocumentLoadError, match="private"):
            APILoader(paginate=True).fetch("https://api.court.test/v1/opinions")
        assert mock_get.call_count == 1

    @patch("requests.get")
    def test_too_many_redirects_is_an_error(self, mock_get):
        mock_get.return_value = _mock_response(
            status_code=302, headers={"Location": "https://docs.test/a.txt"}
        )
        with pytest.raises(DocumentLoadError, match="Too many redirects"):
            URLLoader().fetch("https://docs.test/a.txt")


def test_user_agent_carries_the_package_version():
    assert URLLoader().user_agent.startswith(f"contractex/{__version__} ")
    assert APILoader().user_agent.startswith(f"contractex/{__version__} ")
