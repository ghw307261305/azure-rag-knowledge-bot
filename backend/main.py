import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.services.config import get_settings

settings = get_settings()

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

app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": f"Azure RAG Knowledge Bot API is running in {settings.app_env}"
    }
