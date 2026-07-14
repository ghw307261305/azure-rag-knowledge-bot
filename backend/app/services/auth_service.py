"""Local JWT authentication boundary used before Entra ID is available."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.config import get_settings

ALLOWED_ROLES = {"user", "operator", "admin"}
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """認証結果として API 層へ渡す主体、ロール、アクセスグループ。"""
    subject: str
    role: str
    groups: tuple[str, ...]
    authenticated: bool

    @property
    def access_groups(self) -> set[str] | None:
        return set(self.groups) if self.authenticated else None


def create_local_token(
    subject: str,
    *,
    role: str = "user",
    groups: list[str] | None = None,
    expires_in_seconds: int = 3600,
) -> str:
    """ローカル検証用に、HS256 署名と期限を持つ最小 JWT を生成する。"""
    settings = get_settings()
    if role not in ALLOWED_ROLES:
        raise ValueError(f"role must be one of: {', '.join(sorted(ALLOWED_ROLES))}")
    if not subject or expires_in_seconds <= 0:
        raise ValueError("subject and a positive expiry are required")
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "role": role,
        "groups": sorted(set(groups or [])),
        "iss": settings.local_jwt_issuer,
        "aud": settings.local_jwt_audience,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    encoded_header = _encode_json(header)
    encoded_payload = _encode_json(payload)
    signed = f"{encoded_header}.{encoded_payload}"
    signature = hmac.new(
        settings.local_jwt_secret.encode("utf-8"),
        signed.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signed}.{_base64url_encode(signature)}"


def decode_local_token(token: str) -> Principal:
    """署名・アルゴリズム・期限・必須 claim を検証して主体へ変換する。"""
    settings = get_settings()
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        signed = f"{encoded_header}.{encoded_payload}"
        # compare_digest を使い、署名比較のタイミング差を漏らさない。
        expected_signature = hmac.new(
            settings.local_jwt_secret.encode("utf-8"),
            signed.encode("ascii"),
            hashlib.sha256,
        ).digest()
        actual_signature = _base64url_decode(encoded_signature)
        if not hmac.compare_digest(actual_signature, expected_signature):
            raise ValueError("invalid signature")
        header = json.loads(_base64url_decode(encoded_header))
        payload = json.loads(_base64url_decode(encoded_payload))
    except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail="無効な認証トークンです") from exc

    if header.get("alg") != "HS256":
        raise HTTPException(status_code=401, detail="無効な認証トークンです")
    if payload.get("iss") != settings.local_jwt_issuer:
        raise HTTPException(status_code=401, detail="認証トークンの発行者が不正です")
    if payload.get("aud") != settings.local_jwt_audience:
        raise HTTPException(status_code=401, detail="認証トークンの対象 API が不正です")
    if int(payload.get("exp", 0)) <= int(time.time()):
        raise HTTPException(status_code=401, detail="認証トークンの有効期限が切れています")

    subject = str(payload.get("sub", "")).strip()
    role = str(payload.get("role", "")).strip()
    groups = payload.get("groups", [])
    if not subject or role not in ALLOWED_ROLES or not isinstance(groups, list):
        raise HTTPException(status_code=401, detail="認証トークンのクレームが不正です")
    safe_groups = tuple(
        sorted({str(group).strip() for group in groups if str(group).strip()})
    )
    return Principal(subject, role, safe_groups, True)


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    """AUTH_MODE に応じて匿名主体を許可するか、Bearer JWT を要求する。"""
    settings = get_settings()
    if settings.auth_mode == "disabled":
        return Principal("anonymous-local", "admin", ("*",), False)
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer トークンが必要です")
    return decode_local_token(credentials.credentials)


def require_roles(*allowed_roles: str) -> Callable[[Principal], Principal]:
    """指定ロールのいずれかを持つ主体だけを通す FastAPI 依存関数を作る。"""
    invalid = set(allowed_roles) - ALLOWED_ROLES
    if invalid:
        raise ValueError(f"Unsupported roles: {', '.join(sorted(invalid))}")

    def dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if principal.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="この操作を実行する権限がありません")
        return principal

    return dependency


def _encode_json(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _base64url_encode(raw)


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
