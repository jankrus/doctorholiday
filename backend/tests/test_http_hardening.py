import pytest
from fastapi.testclient import TestClient

ALLOWED = "https://doctorholiday.localhost"
FOREIGN = "https://evil.example.org"


def test_cross_site_post_with_foreign_origin_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout", headers={"Origin": FOREIGN})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert response.json()["error"]["requestId"] == response.headers["X-Request-Id"]


@pytest.mark.parametrize(
    "origin", ["null", ALLOWED + ".evil.example.org", "http://doctorholiday.localhost"]
)
def test_lookalike_and_opaque_origins_are_rejected(client: TestClient, origin: str) -> None:
    assert client.post("/api/v1/auth/logout", headers={"Origin": origin}).status_code == 403


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_every_state_changing_method_is_checked(client: TestClient, method: str) -> None:
    response = client.request(method, "/api/v1/auth/logout", headers={"Origin": FOREIGN})

    assert response.status_code == 403


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_cross_site_fetch_metadata_without_origin_is_rejected(
    client: TestClient, site: str
) -> None:
    response = client.post("/api/v1/auth/logout", headers={"Sec-Fetch-Site": site})

    assert response.status_code == 403


def test_allowed_origin_is_passed_on(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout", headers={"Origin": ALLOWED})

    assert response.status_code != 403


@pytest.mark.parametrize(
    "headers", [{}, {"Sec-Fetch-Site": "same-origin"}, {"Sec-Fetch-Site": "none"}]
)
def test_requests_without_foreign_origin_are_passed_on(
    client: TestClient, headers: dict[str, str]
) -> None:
    assert client.post("/api/v1/auth/logout", headers=headers).status_code != 403


def test_safe_methods_are_not_checked(client: TestClient) -> None:
    response = client.get("/healthz", headers={"Origin": FOREIGN})

    assert response.status_code == 200


def test_cors_preflight_from_foreign_origin_is_not_allowed(client: TestClient) -> None:
    response = client.options(
        "/api/v1/auth/login",
        headers={"Origin": FOREIGN, "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code >= 400
    assert not [name for name in response.headers if name.lower().startswith("access-control-")]


def test_no_response_carries_cors_headers(client: TestClient) -> None:
    response = client.get("/healthz", headers={"Origin": ALLOWED})

    assert not [name for name in response.headers if name.lower().startswith("access-control-")]


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("GET", "/healthz", {}),
        ("GET", "/does-not-exist", {}),
        ("POST", "/api/v1/auth/logout", {"headers": {"Origin": FOREIGN}}),
        (
            "POST",
            "/api/v1/auth/login",
            {"content": b"x", "headers": {"Content-Type": "text/plain"}},
        ),
    ],
)
def test_security_headers_on_every_response(
    client: TestClient, method: str, path: str, kwargs: dict[str, object]
) -> None:
    response = client.request(method, path, **kwargs)  # type: ignore[arg-type]

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "max-age=" in response.headers["Strict-Transport-Security"]
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")


def test_security_headers_on_the_generic_500(app, caplog) -> None:  # type: ignore[no-untyped-def]
    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert response.headers["X-Content-Type-Options"] == "nosniff"
