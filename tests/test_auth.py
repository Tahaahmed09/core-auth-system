"""
End-to-End tests covering all 6 scenarios from the spec:
  1. Registration
  2. Login / Authentication
  3. Protected route access (/me)
  4. Token rotation (refresh)
  5. Logout (blacklist)
  6. Zero-Trust post-logout block
"""
import asyncio
import pytest

from httpx import AsyncClient

TEST_EMAIL = "testuser@example.com"
TEST_PASSWORD = "StrongPass123!"

# ── 1. Registration ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 201
    data = response.json()

    # Spec: UserRegistrationResponse schema
    assert "id" in data
    assert data["email"] == TEST_EMAIL
    assert data["is_active"] is True
    assert data["is_superuser"] is False
    assert "created_at" in data

    # Spec: password must never be returned
    assert "password" not in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    # First registration
    await client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": TEST_PASSWORD},
    )
    # Second registration with same email
    response = await client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 400


# ── 2. Login / Authentication ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "login@example.com", "password": TEST_PASSWORD},
    )
    response = await client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()

    # Spec: TokenExchangeResponse schema
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # Spec: dual-key separation — tokens must be different
    assert data["access_token"] != data["refresh_token"]


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    response = await client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": "wrongpassword"},
    )
    assert response.status_code == 401


# ── 3. Protected Route Access (/me) ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_protected_route_with_valid_token(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "me@example.com", "password": TEST_PASSWORD},
    )
    login_resp = await client.post(
        "/auth/login",
        json={"email": "me@example.com", "password": TEST_PASSWORD},
    )
    access_token = login_resp.json()["access_token"]

    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_protected_route_without_token(client: AsyncClient):
    response = await client.get("/auth/me")
    assert response.status_code in (401, 403)

# ── 4. Token Rotation (Refresh) ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "refresh@example.com", "password": TEST_PASSWORD},
    )
    login_resp = await client.post(
        "/auth/login",
        json={"email": "refresh@example.com", "password": TEST_PASSWORD},
    )
    tokens = login_resp.json()
    refresh_token = tokens["refresh_token"]

    await asyncio.sleep(1)  # ← yeh add karo

    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()

    # Spec: returns fresh TokenExchangeResponse
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # New access token must differ from the old one
    assert data["access_token"] != tokens["access_token"]

@pytest.mark.asyncio
async def test_refresh_with_access_token_fails(client: AsyncClient):
    """Access token must not be accepted by the refresh endpoint."""
    await client.post(
        "/auth/register",
        json={"email": "badrefresh@example.com", "password": TEST_PASSWORD},
    )
    login_resp = await client.post(
        "/auth/login",
        json={"email": "badrefresh@example.com", "password": TEST_PASSWORD},
    )
    access_token = login_resp.json()["access_token"]

    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": access_token},  # Wrong token type
    )
    assert response.status_code == 401


# ── 5. Logout (Blacklist) ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_logout_success(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "logout@example.com", "password": TEST_PASSWORD},
    )
    login_resp = await client.post(
        "/auth/login",
        json={"email": "logout@example.com", "password": TEST_PASSWORD},
    )
    access_token = login_resp.json()["access_token"]

    response = await client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200

    # Spec: StandardActionResponse schema
    data = response.json()
    assert "detail" in data


# ── 6. Zero-Trust Post-Logout Block ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_blacklisted_token_is_rejected(client: AsyncClient):
    """After logout, the same access token must be blocked with 401."""
    await client.post(
        "/auth/register",
        json={"email": "zerotrust@example.com", "password": TEST_PASSWORD},
    )
    login_resp = await client.post(
        "/auth/login",
        json={"email": "zerotrust@example.com", "password": TEST_PASSWORD},
    )
    access_token = login_resp.json()["access_token"]

    # Logout — token goes into blacklist
    await client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    # Spec: must return HTTP 401 when blacklisted token is reused
    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 401