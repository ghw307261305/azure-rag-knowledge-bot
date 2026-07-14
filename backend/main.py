"""FastAPI アプリの初期化、共通ミドルウェア、ルーター登録を行うエントリーポイント。"""

import os
import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.services.config import get_settings, validate_settings
from app.services.logging_service import (
    configure_logging,
    reset_request_id,
    set_request_id,
)
from app.services.telemetry_service import configure_telemetry

settings = get_settings()
validate_settings(settings)
configure_logging(level=settings.log_level, json_logs=settings.json_logs)
logger = logging.getLogger(__name__)

app = FastAPI(title="Azure RAG Knowledge Bot API")

# ローカル開発の許可オリジン
_default_origins = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]

# 本番環境では CORS_ORIGIN 環境変数（Azure SWA の URL など）を追加
_extra = os.getenv("CORS_ORIGIN", "").strip()
allowed_origins = _default_origins + ([_extra] if _extra else [])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request, call_next):
    """リクエスト ID と処理時間を、レスポンスと構造化ログの両方に関連付ける。"""
    # 呼び出し元の ID を引き継ぐことで、フロントエンドからバックエンドまで追跡できる。
    request_id = request.headers.get("X-Request-ID", "").strip() or str(uuid.uuid4())
    token = set_request_id(request_id[:128])
    started_at = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id[:128]
        return response
    finally:
        # 例外時にも必ず完了ログを残し、ContextVar を次のリクエストへ漏らさない。
        logger.info(
            "HTTP request completed",
            extra={
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "latency_ms": round((time.perf_counter() - started_at) * 1000, 3),
            },
        )
        reset_request_id(token)

app.include_router(router)
configure_telemetry(app, settings)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": f"Azure RAG Knowledge Bot API is running in {settings.app_env}"
    }
