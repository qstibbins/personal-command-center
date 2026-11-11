import pytest
from fastapi.testclient import TestClient

from pcc.main import app
from pcc.schemas.capture import MAX_TEXT_LENGTH, MAX_URL_LENGTH

client = TestClient(app)

VALID_URLS = [
    "https://example.com",
    "http://example.com/path?q=1#frag",
    "http://localhost:3000/x",
    "https://sub.example.co.uk:8443/a/b",
    "HTTPS://Example.com/Path",
    "http://127.0.0.1:8000",
    "http://[::1]/",
    "https://münchen.de/straße",
    "https://example.com./",
    "https://example.com/path@with-at",
]

INVALID_URLS = [
    "example.com",
    "www.example.com/page",
    "//example.com",
    "ftp://example.com/file",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "data:text/html,hi",
    "mailto:a@b.com",
    "http://",
    "https://",
    "http:///path",
    "https://exa mple.com",
    "https://a.com https://b.com",
    "https://example.com/\nsecond",
    "https://example.com/\x00",
    "http://.com",
    "http://a..com",
    "http://-bad.com",
    "http://[::1",
    "http://example.com:99999",
    "http://256.256.256.256",
]

CREDENTIAL_URLS = [
    "https://user:secret@example.com/x",
    "https://user@example.com",
    "https://:secret@example.com",
    "https://@example.com",
]


def post(test_client, source_type, content, title=None):
    payload = {"source_type": source_type, "content": content}
    if title is not None:
        payload["title"] = title
    return test_client.post("/api/v1/captures", json=payload)


def assert_content_error(response, fragment=None):
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "content"]
    if fragment:
        assert fragment in error["msg"].lower()


@pytest.mark.parametrize("url", VALID_URLS)
def test_valid_urls_are_stored_exactly_as_submitted(db_client, url):
    response = post(db_client, "url", url)

    assert response.status_code == 201
    assert response.json()["content"] == url


def test_url_is_trimmed_but_not_normalized(db_client):
    response = post(db_client, "url", "  https://Example.com/x \n")

    assert response.status_code == 201
    assert response.json()["content"] == "https://Example.com/x"


def test_url_at_max_length_is_accepted(db_client):
    url = "https://example.com/" + "a" * (MAX_URL_LENGTH - len("https://example.com/"))

    response = post(db_client, "url", url)

    assert response.status_code == 201
    assert len(response.json()["content"]) == MAX_URL_LENGTH


@pytest.mark.parametrize("url", INVALID_URLS)
def test_invalid_urls_are_rejected(url):
    assert_content_error(post(client, "url", url))


@pytest.mark.parametrize("url", CREDENTIAL_URLS)
def test_urls_with_credentials_are_rejected(url):
    assert_content_error(post(client, "url", url), "username or password")


def test_url_over_max_length_is_rejected():
    url = "https://example.com/" + "a" * (MAX_URL_LENGTH - len("https://example.com/") + 1)

    assert_content_error(post(client, "url", url), "2048")


def test_invalid_url_message_mentions_http():
    assert_content_error(post(client, "url", "ftp://example.com"), "http")


@pytest.mark.parametrize("content", ["", "   ", "\n\t "])
@pytest.mark.parametrize("source_type", ["text", "url"])
def test_blank_content_is_rejected_on_the_content_field(source_type, content):
    assert_content_error(post(client, source_type, content), "blank")


def test_rejected_url_is_not_persisted(db_client):
    assert post(db_client, "url", "ftp://example.com").status_code == 422

    assert db_client.get("/api/v1/captures").json() == []


@pytest.mark.parametrize("content", ["not a url", "javascript:alert(1)", "ftp://x.com"])
def test_text_captures_are_not_url_checked(db_client, content):
    response = post(db_client, "text", content)

    assert response.status_code == 201
    assert response.json()["content"] == content


def test_text_is_trimmed_but_internal_whitespace_is_preserved(db_client):
    content = "line one\n\n    indented line\n\tlast"

    response = post(db_client, "text", f"  \n{content}\n  ")

    assert response.status_code == 201
    assert response.json()["content"] == content


def test_text_at_max_length_is_accepted(db_client):
    response = post(db_client, "text", "a" * MAX_TEXT_LENGTH)

    assert response.status_code == 201


def test_text_over_max_length_is_rejected():
    assert_content_error(post(client, "text", "a" * (MAX_TEXT_LENGTH + 1)), "100,000")


def test_text_length_limit_applies_after_trimming(db_client):
    response = post(db_client, "text", f"  {'a' * MAX_TEXT_LENGTH}  ")

    assert response.status_code == 201


def test_title_is_trimmed_and_blank_title_becomes_null(db_client):
    trimmed = post(db_client, "text", "note", title="  T  ")
    blank = post(db_client, "text", "note", title="   ")

    assert trimmed.json()["title"] == "T"
    assert blank.status_code == 201
    assert blank.json()["title"] is None


def test_title_over_300_characters_is_rejected():
    response = post(client, "text", "note", title="t" * 301)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "title"]
