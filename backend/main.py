# backend/main.py
#
# PIE BRIDGE - FastAPI 앱 진입점 (미들웨어 + 구조적 로깅 완전판)
#
# 실행 방법:
#   cd backend
#   uvicorn main:app --reload --port 8000
#
# 로그 파일: backend/logs/pie_bridge.log (날짜별 회전)

import logging
import logging.handlers
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.ai_routes import router as ai_router
from app.core.config import settings
from app.models.database import init_db
from app.services.rag_service import rag_service


# ─────────────────────────────────────────────────────────────
# 로깅 설정
# ─────────────────────────────────────────────────────────────

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def setup_logging() -> None:
    """
    구조적 로깅 설정.
    - 콘솔: INFO 이상, 컬러 없는 간결한 포맷
    - 파일: DEBUG 이상, JSON-like 상세 포맷, 날짜별 자동 회전 (최대 14일 보관)
    """
    # ── 포맷터 ───────────────────────────────────────────────
    console_fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    file_fmt = logging.Formatter(
        fmt='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s",'
            '"msg":%(message)r,"module":"%(module)s","line":%(lineno)d}',
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # ── 핸들러 ───────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_fmt)

    # TimedRotatingFileHandler: 매일 자정 새 파일, 14일 보관
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "pie_bridge.log",
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_fmt)
    file_handler.suffix = "%Y-%m-%d"

    # ── 루트 로거 설정 ────────────────────────────────────────
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # 외부 라이브러리 노이즈 억제
    for noisy in ("httpx", "httpcore", "urllib3", "chromadb", "google"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger("pie_bridge.main")


# ─────────────────────────────────────────────────────────────
# 요청/응답 로깅 미들웨어
# ─────────────────────────────────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    모든 HTTP 요청과 응답을 로깅한다.

    로그 항목:
        → [req_id] METHOD /path  (요청 수신)
        ← [req_id] STATUS  Xms   (응답 완료)

    req_id: 각 요청에 고유한 짧은 UUID (추적 용도)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = str(uuid.uuid4())[:8]  # 8자리 짧은 ID
        start = time.perf_counter()

        # ── 요청 수신 로그 ────────────────────────────────────
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            f"→ [{req_id}] {request.method} {request.url.path} "
            f"from {client_ip}"
        )

        # 요청 객체에 req_id 저장 (라우터에서 접근 가능)
        request.state.req_id = req_id

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"← [{req_id}] 500 INTERNAL ERROR  {elapsed:.1f}ms  "
                f"exception={type(exc).__name__}: {exc}"
            )
            raise

        elapsed = (time.perf_counter() - start) * 1000

        # 상태 코드별 로그 레벨 분기
        log_fn = logger.info if response.status_code < 400 else logger.warning
        log_fn(
            f"← [{req_id}] {response.status_code}  {elapsed:.1f}ms  "
            f"{request.method} {request.url.path}"
        )

        # 응답 헤더에 req_id 추가 (프론트 디버깅용)
        response.headers["X-Request-ID"] = req_id
        return response


# ─────────────────────────────────────────────────────────────
# 앱 수명 주기 (startup / shutdown)
# ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    startup: SQLite 테이블 생성 → ChromaDB RAG 빌드
    shutdown: 로그 플러시
    """
    logger.info("=" * 60)
    logger.info("PIE BRIDGE 백엔드 시작 중...")

    # 1. SQLite 테이블 생성 (없으면)
    await init_db()
    logger.info("SQLite DB 초기화 완료")

    # 2. ChromaDB RAG 빌드 (이미 있으면 건너뜀)
    try:
        logger.info("ChromaDB RAG 빌드 시작...")
        rag_service.build_db(force_rebuild=False, platform="robomation")
        # ⚠️ 일회성 재빌드: 엔트리 RAG 문서 변경 반영 (다음 시작 후 False 로 되돌릴 것)
        rag_service.build_db(force_rebuild=True, platform="entry")
        logger.info("ChromaDB RAG 준비 완료")
    except Exception as e:
        # RAG 실패해도 서버는 기동 (폴백 컨텍스트 사용)
        logger.error(f"ChromaDB 초기화 실패 (폴백 사용): {e}")

    logger.info("PIE BRIDGE 백엔드 준비 완료! http://localhost:8000")
    logger.info("=" * 60)

    yield  # ── 서버 실행 중 ──

    logger.info("PIE BRIDGE 백엔드 종료 중...")
    logging.shutdown()


# ─────────────────────────────────────────────────────────────
# FastAPI 앱 생성
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="PIE BRIDGE API",
    description=(
        "초등학생 블록코딩 → 파이썬 전환 지원 AI 플랫폼\n\n"
        "- Flash 모델: 이미지 분석, 행동 계획\n"
        "- Pro 모델: RAG 기반 파이썬 코드 생성\n"
        "- Safety Filter: 위험 키워드 차단\n"
        "- SQLite: 학생 행동 로그"
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",        # Swagger UI
    redoc_url="/redoc",      # ReDoc UI
)


# ─────────────────────────────────────────────────────────────
# 미들웨어 등록 (아래서 위 순서로 실행됨)
# ─────────────────────────────────────────────────────────────

# 1. GZip 압축 (512 bytes 이상 응답을 자동 압축)
#    - 코드 JSON 응답 크기를 크게 줄여줌
app.add_middleware(GZipMiddleware, minimum_size=512)

# 2. CORS (프론트 개발 서버 및 배포 도메인 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    expose_headers=["X-Request-ID"],  # 프론트에서 헤더 읽기 허용
)

# 3. 요청/응답 로깅 (가장 바깥쪽 → 모든 요청 포착)
app.add_middleware(RequestLoggingMiddleware)


# ─────────────────────────────────────────────────────────────
# 라우터 등록
# ─────────────────────────────────────────────────────────────

app.include_router(ai_router)


# ─────────────────────────────────────────────────────────────
# 기본 엔드포인트
# ─────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"], summary="서버 상태 확인")
async def health_check():
    """서버가 정상적으로 실행 중인지 확인합니다."""
    return {
        "status": "ok",
        "message": "PIE BRIDGE 서버가 실행 중이에요! 🐹",
        "version": app.version,
        "docs": "/docs",
    }


@app.get("/health/rag", tags=["Health"], summary="RAG DB 상태 확인")
async def rag_health():
    """ChromaDB RAG 컬렉션 상태를 반환합니다."""
    try:
        collection = rag_service._collection
        if collection is None:
            return {"status": "not_built", "count": 0}
        count = collection.count()
        return {"status": "ok", "chunk_count": count}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
