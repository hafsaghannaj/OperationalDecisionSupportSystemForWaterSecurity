from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from fastapi import HTTPException, status

from services.api.app.config import Settings, get_settings


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _base64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(f"{raw}{padding}".encode("ascii"))


def _json_dumps(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _setting(settings: Settings | Any, name: str, default: Any) -> Any:
    return getattr(settings, name, default)


@dataclass(slots=True)
class AuthenticatedActor:
    operator_id: str
    roles: tuple[str, ...]
    auth_method: str

    def has_any_role(self, required_roles: Iterable[str]) -> bool:
        required = {role.strip().lower() for role in required_roles if role.strip()}
        if not required:
            return True
        actor_roles = {role.strip().lower() for role in self.roles}
        return bool(actor_roles & required)


def create_operator_token(
    *,
    operator_id: str,
    roles: Iterable[str],
    secret: str,
    issuer: str = "odssws",
    audience: str = "odssws-operators",
    expires_in: timedelta = timedelta(hours=12),
    now: datetime | None = None,
) -> str:
    if not operator_id.strip():
        raise ValueError("operator_id must not be blank.")
    if not secret:
        raise ValueError("secret must not be blank.")

    issued_at = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    expires_at = issued_at + expires_in
    normalized_roles = sorted({role.strip().lower() for role in roles if role.strip()})
    if not normalized_roles:
        raise ValueError("roles must contain at least one non-blank role.")

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": operator_id.strip(),
        "roles": normalized_roles,
        "iss": issuer,
        "aud": audience,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    signing_input = ".".join(
        [
            _base64url_encode(_json_dumps(header).encode("utf-8")),
            _base64url_encode(_json_dumps(payload).encode("utf-8")),
        ]
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_base64url_encode(signature)}"


def verify_operator_token(
    token: str,
    *,
    secret: str,
    issuer: str = "odssws",
    audience: str = "odssws-operators",
    now: datetime | None = None,
) -> AuthenticatedActor:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed bearer token.") from exc

    signing_input = f"{encoded_header}.{encoded_payload}"
    expected_signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    actual_signature = _base64url_decode(encoded_signature)
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token signature.")

    try:
        payload = json.loads(_base64url_decode(encoded_payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token payload is invalid.") from exc

    current_time = now or datetime.now(timezone.utc)
    if payload.get("iss") != issuer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token issuer mismatch.")
    if payload.get("aud") != audience:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token audience mismatch.")
    if int(payload.get("exp", 0)) <= int(current_time.timestamp()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token has expired.")

    operator_id = str(payload.get("sub", "")).strip()
    roles = tuple(str(role).strip().lower() for role in payload.get("roles", []) if str(role).strip())
    if not operator_id or not roles:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token is missing operator claims.")

    return AuthenticatedActor(
        operator_id=operator_id,
        roles=roles,
        auth_method="bearer",
    )


def authorize_write_request(
    *,
    required_roles: Iterable[str] = (),
    bearer_token: str | None = None,
    api_key: str | None = None,
    settings: Settings | Any | None = None,
) -> AuthenticatedActor | None:
    resolved_settings = settings or get_settings()
    auth_token_secret = str(_setting(resolved_settings, "auth_token_secret", "") or "")
    auth_issuer = str(_setting(resolved_settings, "auth_issuer", "odssws") or "odssws")
    auth_audience = str(_setting(resolved_settings, "auth_audience", "odssws-operators") or "odssws-operators")
    configured_api_key = str(_setting(resolved_settings, "api_key", "") or "")
    allow_legacy_api_key = bool(_setting(resolved_settings, "allow_legacy_api_key", False))

    actor: AuthenticatedActor | None = None
    if auth_token_secret:
        if bearer_token:
            actor = verify_operator_token(
                bearer_token,
                secret=auth_token_secret,
                issuer=auth_issuer,
                audience=auth_audience,
            )
        elif configured_api_key and allow_legacy_api_key and api_key == configured_api_key:
            actor = AuthenticatedActor(
                operator_id="legacy-api-key",
                roles=("operator", "admin"),
                auth_method="api_key",
            )
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid bearer token.")
    elif configured_api_key:
        if api_key != configured_api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key.")
        actor = AuthenticatedActor(
            operator_id="legacy-api-key",
            roles=("operator", "admin"),
            auth_method="api_key",
        )
    else:
        return None

    if actor is not None and not actor.has_any_role(required_roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient operator role for this action.")
    return actor
