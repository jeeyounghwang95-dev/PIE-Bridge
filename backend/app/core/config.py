# backend/app/core/config.py
#
# 환경 변수 및 모델 설정
# .env 파일에 GEMINI_API_KEY=your_key 를 넣어 두세요.

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# 이 파일(config.py)을 기준으로 backend/.env 절대 경로를 계산
# backend/app/core/config.py → backend/.env
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    # ── Gemini API ──────────────────────────────────────────
    GEMINI_API_KEY: str = ""

    # 하이브리드 모델 이름 (변경 시 여기만 수정)
    FLASH_MODEL: str = "gemini-2.5-flash"
    PRO_MODEL: str = "gemini-2.5-pro"

    # ── Anthropic API (1-B 행동 계획 생성용) ────────────────
    ANTHROPIC_API_KEY: str = ""
    # PLAN_MODEL: Claude 모델 → Gemini로 되돌리려면 "gemini-2.5-flash" 로 변경
    PLAN_MODEL: str = "claude-haiku-4-5-20251001"

    # ── PostgreSQL (Supabase) ───────────────────────────────
    # 형식: postgresql+asyncpg://user:password@host:5432/dbname
    DATABASE_URL: str = ""

    # ── CORS ───────────────────────────────────────────────
    # 환경변수 ALLOWED_ORIGINS에 콤마로 구분해서 설정 가능
    # 예: "https://pie-bridge.vercel.app,http://localhost:5173"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
    )


settings = Settings()
