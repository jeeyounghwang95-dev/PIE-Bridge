# backend/app/models/database.py
#
# PIE BRIDGE - SQLite 데이터베이스 스키마 및 세션 관리
#
# 테이블:
#   action_logs  - 학생 행동 기록 (단계, 선택, 타임스탬프)
#   safety_logs  - 안전 필터 차단 기록

from sqlalchemy import Column, Integer, String, BigInteger
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# ── 비동기 엔진 생성 ─────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,   # SQL 로그 확인하려면 True 로 변경
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


# ── 베이스 클래스 ────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── action_logs 테이블 ───────────────────────────────────────
class ActionLog(Base):
    """
    학생이 각 단계에서 무엇을 했는지 기록한다.

    예) stage="code_generated", choice=2 → "안전하게 계획하기 선택 후 코드 생성"
    """
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    stage = Column(String(50), nullable=False)         # image_analysis / plan_generated / code_generated
    choice = Column(Integer, nullable=True)             # 1~5 (2단계 선택지), NULL이면 선택 없음
    detail = Column(String(500), nullable=True)         # 추가 메모 (목표 텍스트, 성공/실패 등)
    timestamp = Column(BigInteger, nullable=False)      # Unix timestamp (초)


# ── safety_logs 테이블 ──────────────────────────────────────
class SafetyLog(Base):
    """
    안전 필터에 차단된 입력을 기록한다.
    교사/관리자 대시보드에서 모니터링 용도.
    """
    __tablename__ = "safety_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    input_text = Column(String(500), nullable=False)   # 차단된 원문
    reason = Column(String(50), nullable=False)         # danger_speed / danger_action / profanity
    timestamp = Column(BigInteger, nullable=False)


# ── DB 초기화 함수 ───────────────────────────────────────────
async def init_db() -> None:
    """
    앱 시작 시 테이블이 없으면 자동 생성한다.
    main.py 의 lifespan 이벤트에서 호출한다.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── 세션 의존성 (FastAPI Depends 용) ────────────────────────
async def get_db():
    """
    요청마다 DB 세션을 열고, 요청 종료 시 자동으로 닫는다.
    FastAPI 라우터에서 Depends(get_db) 로 주입한다.
    """
    async with AsyncSessionLocal() as session:
        yield session
