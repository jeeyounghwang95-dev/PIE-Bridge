# backend/app/api/ai_routes.py
#
# PIE BRIDGE - FastAPI 라우터
#
# 엔드포인트 목록:
#   POST /api/ai/analyze-image   → 1-A단계: 이미지 품질 검사
#   POST /api/ai/generate-plan   → 1-B단계: 행동 계획 생성
#   POST /api/ai/generate-code   → 3단계:  파이썬 코드 생성 (2단계 선택 포함)
#
# 모든 엔드포인트는 SQLite에 비동기 로그를 남긴다.

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.core.safety_filter import safety_filter
from app.models.database import get_db, ActionLog, SafetyLog
from app.services.gemini_service import (
    analyze_image_quality,
    generate_action_plan,
    generate_python_code,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/ai", tags=["AI"])


# ─────────────────────────────────────────────────────────────
# Request / Response 스키마 (Pydantic)
# ─────────────────────────────────────────────────────────────

class ImageAnalysisRequest(BaseModel):
    """1-A단계: 이미지 품질 검사 요청"""
    base64_image: str = Field(..., description="프론트에서 리사이징된 base64 이미지")
    user_id: str = Field(default="anonymous", description="학생 식별자")
    lang: str = Field(default="ko", description="UI 언어: 'ko' 또는 'en' — AI 자연어 출력에만 영향")


class ObstacleItem(BaseModel):
    name: str = ""
    position: str = ""


class PlanRequest(BaseModel):
    """1-B단계: 행동 계획 생성 요청"""
    base64_image: str = Field(..., description="품질 검사를 통과한 base64 이미지")
    student_goal: str = Field(..., min_length=1, max_length=200, description="학생이 입력한 목표")
    obstacles: list[ObstacleItem] = Field(
        default_factory=list,
        description="이미지 분석에서 감지된 장애물 목록 ({name, position})",
    )
    user_id: str = Field(default="anonymous")
    board_detected: bool = Field(default=False, description="사진에서 말판(격자 보드) 감지 여부")
    hamster_facing: str = Field(default="unknown", description="햄스터봇 방향: toward_camera | away_from_camera | left | right | unknown")
    hamster_position: str = Field(default="", description="햄스터봇이 사진에서 위치한 곳 설명")
    lang: str = Field(default="ko", description="UI 언어: 'ko' 또는 'en' — AI 자연어 출력에만 영향")


class CodeRequest(BaseModel):
    """3단계: 파이썬 코드 생성 요청 (2단계 선택 포함)"""
    action_plan: dict[str, Any] = Field(..., description="1-B단계에서 생성된 행동 계획 JSON")
    student_choice: int = Field(..., ge=1, le=5, description="학생이 선택한 옵션 번호 (1~5)")
    user_id: str = Field(default="anonymous")
    platform: str = Field(default="entry", description="코드 플랫폼: 'entry' 또는 'robomation'")
    board_detected: bool = Field(default=False, description="사진에서 말판(격자 보드) 감지 여부")
    student_goal: str = Field(default="", description="학생이 입력한 원본 목표 텍스트")
    hamster_position: str = Field(default="", description="햄스터봇 위치 설명 (1단계 분석 결과)")
    obstacles: list[ObstacleItem] = Field(
        default_factory=list,
        description="1단계에서 감지된 장애물 목록 ({name, position})",
    )
    lang: str = Field(default="ko", description="UI 언어: 'ko' 또는 'en' — AI 자연어 출력에만 영향")


class SafetyBlockedResponse(BaseModel):
    """안전 필터 차단 시 반환 스키마"""
    blocked: bool = True
    message: str


# ─────────────────────────────────────────────────────────────
# 1-A단계: 이미지 품질 검사 엔드포인트
# ─────────────────────────────────────────────────────────────

@router.post("/analyze-image")
async def analyze_image(
    req: ImageAnalysisRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    웹캠 사진의 품질을 Flash 모델로 검사한다.

    - 합격 시: {"passed": true, ...}  → 프론트는 목표 입력 UI를 보여줌
    - 불합격 시: {"passed": false, "reason": "..."}  → 프론트는 재촬영 안내 UI를 보여줌
    """
    # base64 최소 길이 체크 (빈 이미지 방어)
    if len(req.base64_image) < 100:
        raise HTTPException(status_code=400, detail="이미지 데이터가 올바르지 않아요.")

    result = await analyze_image_quality(req.base64_image, lang=req.lang)

    # 이미지 분석 로그 저장 (비동기, 실패해도 응답에는 영향 없음)
    await _log_action(
        db=db,
        user_id=req.user_id,
        stage="image_analysis",
        choice=None,
        detail=str(result.get("passed")),
    )

    return result


# ─────────────────────────────────────────────────────────────
# 1-B단계: 행동 계획 생성 엔드포인트
# ─────────────────────────────────────────────────────────────

@router.post("/generate-plan")
async def generate_plan(
    req: PlanRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    학생의 목표를 받아 Flash 모델로 3단계 행동 계획을 생성한다.

    ⚠️  안전 필터: 목표 텍스트에 위험 키워드가 있으면 즉시 차단.
    """
    # ── 안전 필터 검사 ──────────────────────────────────────
    filter_result = safety_filter.check(req.student_goal)
    if filter_result["blocked"]:
        # 차단 내역을 safety_logs 테이블에 저장
        await _log_safety(
            db=db,
            user_id=req.user_id,
            input_text=req.student_goal,
            reason=filter_result["reason"],
        )
        return SafetyBlockedResponse(
            message=filter_result["message"]
        ).model_dump()

    # ── 계획 생성 ──────────────────────────────────────────
    plan = await generate_action_plan(
        base64_image=req.base64_image,
        student_goal=req.student_goal,
        obstacles=[o.model_dump() for o in req.obstacles],
        board_detected=req.board_detected,
        hamster_facing=req.hamster_facing,
        hamster_position=req.hamster_position,
        lang=req.lang,
    )

    # 햄스터봇 움직임과 무관한 입력 감지
    if plan.get("irrelevant"):
        await _log_safety(
            db=db,
            user_id=req.user_id,
            input_text=req.student_goal,
            reason="irrelevant_input",
        )
        if req.lang == "en":
            irrelevant_msg = (
                "Your input doesn't seem related to moving the Hamster robot or its goal.\n"
                "Please describe specifically how you want the Hamster robot to move.\n"
                "e.g., 'Go around the book and stop in front of the eraser.'"
            )
        else:
            irrelevant_msg = (
                "입력한 내용이 햄스터봇의 움직임이나 목표와 관련이 없어 보여요.\n"
                "구체적으로 햄스터봇이 어떻게 움직였으면 좋겠는지 다시 써주세요.\n"
                "예: '책 옆을 돌아서 지우개 앞으로 가줘'"
            )
        return SafetyBlockedResponse(message=irrelevant_msg).model_dump()

    await _log_action(
        db=db,
        user_id=req.user_id,
        stage="plan_generated",
        choice=None,
        detail=req.student_goal,
    )

    return plan


# ─────────────────────────────────────────────────────────────
# 3단계: 파이썬 코드 생성 엔드포인트 (2단계 선택 포함)
# ─────────────────────────────────────────────────────────────

@router.post("/generate-code")
async def generate_code(
    req: CodeRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    학생의 선택(1~5)을 반영해 flash 모델로 파이썬 코드를 생성한다.

    선택지 3번(다시 계획 생성하기)은 코드를 생성하지 않고
    프론트가 1단계로 돌아가도록 안내 메시지를 반환한다.
    """
    # 선택지 3(다시 계획)은 더 이상 코드 생성 라우트로 오지 않음.
    # 프론트가 /generate-plan 을 직접 다시 호출해 같은 위치에서 계획만 새로 만든다.
    if req.student_choice == 3:
        await _log_action(
            db=db,
            user_id=req.user_id,
            stage="code_request",
            choice=3,
            detail="legacy_replan_call",
        )
        replan_msg = (
            "Press the 'Replan' button above to make a new plan."
            if req.lang == "en"
            else "다시 계획을 세우려면 위쪽 '계획 다시 세우기' 버튼을 눌러 주세요."
        )
        return {
            "replan": True,
            "message": replan_msg,
        }

    # ── 선택지 1,2,4,5: 코드 생성 ─────────────────────────
    # rag_context="" 로 두면 gemini_service 내부에서
    # 행동 계획을 쿼리로 ChromaDB RAG 검색을 자동 수행합니다.
    result = await generate_python_code(
        action_plan=req.action_plan,
        student_choice=req.student_choice,
        platform=req.platform,
        rag_context="",
        board_detected=req.board_detected,
        student_goal=req.student_goal,
        hamster_position=req.hamster_position,
        obstacles=[o.model_dump() for o in req.obstacles],
        lang=req.lang,
    )

    # 학생 선택 로그 저장
    await _log_action(
        db=db,
        user_id=req.user_id,
        stage="code_generated",
        choice=req.student_choice,
        detail="success" if "python_code" in result else "parse_error",
    )

    return result


# ─────────────────────────────────────────────────────────────
# 내부 헬퍼: DB 로깅 함수 (실패해도 메인 흐름 중단 안 함)
# ─────────────────────────────────────────────────────────────

async def _log_action(
    db: AsyncSession,
    user_id: str,
    stage: str,
    choice: int | None,
    detail: str,
) -> None:
    """action_logs 테이블에 학생 행동 기록."""
    try:
        log = ActionLog(
            user_id=user_id,
            stage=stage,
            choice=choice,
            detail=detail,
            timestamp=int(time.time()),
        )
        db.add(log)
        await db.commit()
    except Exception:
        # 로깅 실패는 무시 (사용자 경험 우선)
        await db.rollback()


async def _log_safety(
    db: AsyncSession,
    user_id: str,
    input_text: str,
    reason: str,
) -> None:
    """safety_logs 테이블에 차단된 입력 기록."""
    try:
        log = SafetyLog(
            user_id=user_id,
            input_text=input_text,
            reason=reason,
            timestamp=int(time.time()),
        )
        db.add(log)
        await db.commit()
    except Exception:
        await db.rollback()
