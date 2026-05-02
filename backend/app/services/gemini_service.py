# backend/app/services/gemini_service.py
#
# PIE BRIDGE - Gemini AI 서비스 (Flash / Pro 하이브리드 라우팅)
#
# SDK: google-genai (신규 공식 SDK, google-generativeai 대체)
#
# ┌─────────────────────────────────────────────────────────────┐
# │  호출 흐름                                                  │
# │  1단계  이미지 품질 검사 + 행동 계획 생성  →  Flash 모델   │
# │  3단계  RAG 기반 파이썬 코드 생성         →  Pro   모델   │
# └─────────────────────────────────────────────────────────────┘

import asyncio
import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)

# ── 전역 시스템 프롬프트 페르소나 ──────────────────────────────
SYSTEM_PERSONA_KO = (
    "너는 초등학교 선생님이야. "
    "초등학생이 이해하기 쉬운 단어와 다정하고 친절한 존댓말(해요체)을 쓰고, "
    "절대로 위험하거나 불쾌한 내용은 출력하지 마. "
    "답변은 항상 질문자의 언어에 맞춰 자연스러운 존댓말로 제공해."
)
SYSTEM_PERSONA_EN = (
    "You are an elementary school teacher. "
    "Use simple, friendly English that an elementary school student can easily understand. "
    "Never output anything dangerous or offensive. "
    "Always respond entirely in natural English, regardless of the language used in any "
    "system, reference, or scaffolding text in the prompt."
)
# 하위 호환을 위해 기본값 노출 (다른 모듈이 import 할 수 있음)
SYSTEM_PERSONA = SYSTEM_PERSONA_KO


def _persona(lang: str) -> str:
    return SYSTEM_PERSONA_EN if lang == "en" else SYSTEM_PERSONA_KO

# ── 로보메이션 랩 전용 시스템 가이드 ───────────────────────────
# RobomationLAB User_Guide Wiki(https://github.com/RobomationLAB/User_Guide/)
# 의 공식 코딩 규칙을 절대 원칙으로 준수해야 한다.
# RAG 컨텍스트로 전달되는 햄스터-S API 문서는 이 위키에서 발췌한 공식 문서이며,
# 단 한 가지 규칙이라도 어긋나면 잘못된 코드로 간주된다.
ROBOMATION_WIKI_DIRECTIVE = (
    "## RobomationLAB 공식 코딩 규칙 (절대 원칙)\n"
    "너는 RobomationLAB 공식 위키(https://github.com/RobomationLAB/User_Guide/)를\n"
    "학습한 전문가로서, 아래 원칙을 한 치도 어기지 않고 코드를 생성해야 한다.\n"
    "\n"
    "1. 아래 '햄스터-S API 레퍼런스'는 RobomationLAB 위키에서 발췌한 공식 문서이며,\n"
    "   이것이 유일한 진실 원본(source of truth)이다.\n"
    "2. 위키에 명시되지 않은 함수/문법/패턴은 절대 사용하지 않는다.\n"
    "   (예: 일반 Python `import` 패턴, 임의의 클래스 인스턴스화 금지)\n"
    "3. 코딩 규칙에 명시된 모든 형식과 규칙을 철저히 준수해야 한다.\n"
    "   하나라도 어긋나면 잘못된 코드로 간주된다.\n"
    "4. 플랫폼 내에서 일관된 형식의 코드를 생성한다.\n"
    "   (들여쓰기, 함수 시그니처, 메타 접근자 표기 등 위키 예시와 동일하게)\n"
    "5. 모든 코드는 RobomationLAB Block Composer 환경에서 즉시 실행 가능해야 한다.\n"
)

# ── Gemini 클라이언트 (지연 초기화 - API 키 없이 임포트 가능) ─
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """API 키가 필요한 첫 호출 시점에 클라이언트를 생성한다."""
    global _client
    if _client is None:
        if not settings.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY가 설정되지 않았어요. "
                "backend/.env 파일에 GEMINI_API_KEY=... 를 추가해 주세요."
            )
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


# ── Anthropic 클라이언트 (지연 초기화) ───────────────────────
_anthropic_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        try:
            import anthropic as _anthropic_sdk
        except ImportError:
            raise ImportError(
                "anthropic 패키지가 없어요. "
                "pip install anthropic 을 실행해 주세요."
            )
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY가 설정되지 않았어요. "
                "backend/.env 파일에 ANTHROPIC_API_KEY=... 를 추가해 주세요."
            )
        _anthropic_client = _anthropic_sdk.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic_client


def _is_claude_model(model: str) -> bool:
    return model.startswith("claude-")


async def _generate_plan_claude(prompt: str, lang: str = "ko") -> str:
    """Claude 모델로 1-B 행동 계획을 생성한다. 순수 텍스트를 반환."""
    client = _get_anthropic_client()
    system_msg = _persona(lang)
    try:
        msg = await client.messages.create(
            model=settings.PLAN_MODEL,
            max_tokens=4096,
            system=system_msg,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        err = str(e)
        if "529" in err or "overloaded" in err.lower():
            logger.warning(f"Claude {settings.PLAN_MODEL} 과부하 → 3초 후 재시도")
            await asyncio.sleep(3)
            msg = await client.messages.create(
                model=settings.PLAN_MODEL,
                max_tokens=4096,
                system=system_msg,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text
        raise


# ── 단계별 GenerateContentConfig ─────────────────────────────
# response_mime_type="application/json" → 모델이 마크다운 없이
# 순수 JSON만 반환하도록 강제 (JSON 파싱 실패 방지)
#
# thinking_budget 은 단계별로 다르게 설정:
#   - 1-A (이미지 품질 검사): 단순 분류 → 0 (thinking 불필요)
#   - 1-B (행동 계획 생성): 공간 추론 + 경로 계획 → 1024
#   - 3 (코드 생성): RAG 기반 정밀 코딩 → 2048
# max_output_tokens = thinking + 실제출력 합계 예산이므로
# thinking 을 쓸 땐 넉넉히 8192 로 설정해 JSON 잘림 방지.

def _quality_config(lang: str = "ko") -> types.GenerateContentConfig:
    """1-A 이미지 품질 검사용 (thinking 끔)"""
    return types.GenerateContentConfig(
        system_instruction=_persona(lang),
        temperature=0.4,
        max_output_tokens=4096,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )


def _plan_config(lang: str = "ko") -> types.GenerateContentConfig:
    """1-B 행동 계획 생성용 (thinking 유지)"""
    return types.GenerateContentConfig(
        system_instruction=_persona(lang),
        temperature=0.4,
        max_output_tokens=8192,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=1024),
    )


def _code_config(lang: str = "ko") -> types.GenerateContentConfig:
    """3 파이썬 코드 생성용 (thinking 더 많이)"""
    return types.GenerateContentConfig(
        system_instruction=_persona(lang),
        temperature=0.2,
        max_output_tokens=8192,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=2048),
    )

# gemini-2.5 가 503일 때 폴백으로 쓸 모델 (lite는 별도 할당량)
_FLASH_FALLBACK = "gemini-2.5-flash-lite"


# ─────────────────────────────────────────────────────────────
# 헬퍼: 503 재시도 포함 generate_content 래퍼
# ─────────────────────────────────────────────────────────────
async def _generate(model: str, fallback: str, contents, config):
    """
    503 UNAVAILABLE(서버 과부하)이면 3초 대기 후 최대 3회 재시도.
    재시도 후에도 실패하면 fallback 모델로 1회 시도.
    """
    last_exc = None
    for attempt in range(3):
        try:
            return await _get_client().aio.models.generate_content(
                model=model, contents=contents, config=config,
            )
        except Exception as e:
            last_exc = e
            err_str = str(e)
            if "503" in err_str or "UNAVAILABLE" in err_str:
                wait = 3 * (attempt + 1)
                logger.warning(f"{model} 503 (시도 {attempt+1}/3) → {wait}초 대기 후 재시도")
                await asyncio.sleep(wait)
            elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                logger.warning(f"{model} 429 할당량 초과 → {fallback} 폴백")
                return await _get_client().aio.models.generate_content(
                    model=fallback, contents=contents, config=config,
                )
            else:
                raise  # 그 외 에러는 즉시 전파

    # 3회 모두 503 → fallback 모델 시도
    logger.warning(f"{model} 3회 모두 503 → {fallback} 폴백")
    return await _get_client().aio.models.generate_content(
        model=fallback, contents=contents, config=config,
    )


# ─────────────────────────────────────────────────────────────
# 헬퍼: base64 이미지 → SDK Part 객체
# ─────────────────────────────────────────────────────────────
def _image_part(base64_str: str, mime_type: str = "image/jpeg") -> types.Part:
    """프론트에서 받은 base64 이미지를 Gemini Part 형식으로 변환."""
    # data:image/jpeg;base64,... 헤더가 붙어 있으면 제거
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    return types.Part.from_bytes(
        data=base64_str.encode() if isinstance(base64_str, str) else base64_str,
        mime_type=mime_type,
    )


def _image_part_inline(base64_str: str, mime_type: str = "image/jpeg") -> dict:
    """SDK inline_data dict 형식 (Part 미지원 시 폴백)."""
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    import base64 as b64lib
    return types.Part(
        inline_data=types.Blob(
            mime_type=mime_type,
            data=b64lib.b64decode(base64_str),
        )
    )


# ─────────────────────────────────────────────────────────────
# 헬퍼: 응답 텍스트에서 JSON 블록 추출
# ─────────────────────────────────────────────────────────────
def _extract_json(text: str) -> dict:
    """
    모델 응답에서 ```json ... ``` 코드 블록 또는 순수 JSON을 파싱.
    파싱 실패 시 {"raw": text} 반환.
    """
    # 1순위: ```json ... ``` 코드 블록
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 2순위: 가장 바깥쪽 { } 블록을 브레이스 카운팅으로 정확히 추출
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    logger.warning(f"JSON 파싱 실패. 원문 반환. 시작: {text[:80]!r}")
    return {"raw": text}


# ─────────────────────────────────────────────────────────────
# 1-A단계: 이미지 품질 검사  (Flash)
# ─────────────────────────────────────────────────────────────
async def analyze_image_quality(base64_image: str, lang: str = "ko") -> dict[str, Any]:
    """
    웹캠 사진을 받아 촬영 품질과 햄스터봇 유무를 판정한다.

    반환 예시 (합격):
        {"passed": true, "reason": "사진이 선명하고 햄스터봇이 잘 보여요.",
         "hamster_detected": true,
         "hamster_position": "사진 가운데 아래쪽",
         "obstacles_detected": [
            {"name": "책", "position": "햄스터봇 기준 오른쪽 위"},
            {"name": "지우개", "position": "햄스터봇 기준 왼쪽 옆"}
         ]}
    반환 예시 (불합격):
        {"passed": false, "reason": "사진이 너무 흐려요. 다시 찍어볼까요?",
         "hamster_detected": false, "obstacles_detected": []}
    """
    lang_directive = ""
    if lang == "en":
        lang_directive = (
            "## LANGUAGE REQUIREMENT (override any other language hint)\n"
            "All natural-language string fields in the JSON output ('reason', 'hamster_position', "
            "and every obstacle 'name' and 'position') MUST be written in natural English. "
            "Keep enum-like values ('toward_camera', 'left', etc.) exactly as defined.\n"
            "For obstacle 'position', still pick from the same 8 directions but in English: "
            "'directly in front' / 'directly behind' / 'to the left' / 'to the right' / "
            "'front-left' / 'front-right' / 'back-left' / 'back-right'.\n\n"
        )
    prompt = (
        f"{lang_directive}"
        "아래 사진을 보고 다음 기준으로 품질을 검사해 줘.\n"
        "반드시 JSON 형식으로만 대답해. 이모지(이모티콘)는 절대 사용하지 마.\n\n"
        "## 가장 먼저 할 일: 햄스터봇의 '앞(정면)' 방향 확정\n"
        "햄스터봇 윗면에는 진행 방향을 나타내는 화살표 스티커가 붙어 있어.\n"
        "이 화살표가 가리키는 방향이 '봇의 앞(정면, forward)'이야.\n"
        "이것이 이후 모든 위치·방향 판단의 **유일한 기준축**이야.\n"
        "화살표가 보이지 않을 때만 아래 외형 힌트로 앞면을 추정해:\n"
        "  - 앞면: 전체가 흰색이고 가운데 빛감지 센서(작은 구멍), 양쪽에 적외선 근접 센서 2개\n"
        "  - 뒷면: 햄스터봇 색깔(빨강·초록·노랑·파랑)로 채워진 면\n"
        "  - 옆면: 바퀴가 측면에 보임\n\n"
        "## 봇 기준 4방향 정의 (매우 중요)\n"
        "화살표가 가리키는 방향을 '앞'이라고 했을 때:\n"
        "  - 앞(front)    = 화살표가 가리키는 방향\n"
        "  - 뒤(back)     = 화살표 반대 방향\n"
        "  - 왼쪽(left)   = 화살표 기준 시계 반대 방향 90도 (봇이 앞을 볼 때 봇의 왼손 쪽)\n"
        "  - 오른쪽(right)= 화살표 기준 시계 방향 90도 (봇이 앞을 볼 때 봇의 오른손 쪽)\n"
        "사진의 '위쪽/아래쪽'과는 전혀 무관해. 오직 화살표만 보고 판단해.\n\n"
        "## 검사 항목\n"
        "1. 사진이 충분히 선명한가? (흔들림, 어두움 여부)\n"
        "2. 햄스터봇(작은 로봇)이 사진에 보이는가?\n"
        "3. 햄스터봇이 사진의 어디에 위치해 있는가? (예: 사진 가운데 아래쪽 — 이것만 사진 프레임 표현 허용)\n"
        "4. 주변에 어떤 장애물(물건)이 있고, 각 장애물이 햄스터봇을 기준으로 어느 방향에 있는가?\n"
        "   **위치 어휘는 반드시 아래 8가지 중에서만 골라**:\n"
        "     '바로 앞' / '바로 뒤' / '왼쪽 옆' / '오른쪽 옆' /\n"
        "     '앞 왼쪽' / '앞 오른쪽' / '뒤 왼쪽' / '뒤 오른쪽'\n"
        "   ※ '위/아래/상단/하단' 같은 사진 프레임 어휘는 **절대 금지**. 오직 앞/뒤/왼쪽/오른쪽만 사용.\n"
        "   거리감이 명확하면 '약 ~cm' 또는 '가까이/멀리' 같은 표현을 덧붙여도 좋아.\n"
        "   판단 절차:\n"
        "     (a) 사진에서 화살표 끝이 가리키는 방향을 확인 (이게 '봇의 앞')\n"
        "     (b) 봇 위치에서 화살표 방향으로 뻗은 선이 '앞/뒤' 축, 직각으로 뻗은 선이 '왼/오른' 축\n"
        "     (c) 각 장애물이 이 두 축 기준 어느 사분면에 있는지 보고 8방향 중 하나로 분류\n"
        "5. 햄스터봇 아래에 격자 말판 또는 발판(체스판 모양의 보드, 격자선이 있는 보드, 또는 햄스터봇이 올라가 있는 사각형 발판/매트)이 보이는가?\n"
        "   - 말판/발판이 있으면 board_detected=true\n"
        "   - 없으면 board_detected=false\n\n"
        "6. hamster_facing: 화살표가 카메라 프레임 기준 어느 방향을 가리키는가? (참고용)\n"
        "   - 'toward_camera': 화살표가 카메라 쪽을 향함\n"
        "   - 'away_from_camera': 화살표가 카메라 반대 방향을 향함\n"
        "   - 'left': 화살표가 사진 왼쪽을 가리킴\n"
        "   - 'right': 화살표가 사진 오른쪽을 가리킴\n"
        "   - 'up': 화살표가 사진 위쪽을 가리킴\n"
        "   - 'down': 화살표가 사진 아래쪽을 가리킴\n"
        "   - 'unknown': 화살표·외형 모두 판단 불가\n\n"
        'JSON 스키마:\n'
        '{\n'
        '  "passed": true/false,\n'
        '  "reason": "학생에게 보여줄 친절한 이유 (이모지 사용 금지)",\n'
        '  "hamster_detected": true/false,\n'
        '  "hamster_position": "사진에서 햄스터봇이 있는 위치 (한국어 한 줄)",\n'
        '  "board_detected": true/false,\n'
        '  "hamster_facing": "toward_camera" | "away_from_camera" | "left" | "right" | "up" | "down" | "unknown",\n'
        '  "obstacles_detected": [\n'
        '    {"name": "장애물 이름", "position": "8방향 어휘 중 하나 (+ 선택적 거리 표현)"}\n'
        '  ]\n'
        '}'
    )

    image = _image_part_inline(base64_image)
    response = await _generate(
        model=settings.FLASH_MODEL,
        fallback=_FLASH_FALLBACK,
        contents=[image, prompt],
        config=_quality_config(lang),
    )
    result = _extract_json(response.text)

    # 장애물 형식 정규화: 모델이 문자열 배열을 돌려주는 경우 객체 배열로 변환
    obstacles = result.get("obstacles_detected") or []
    normalized = []
    for item in obstacles:
        if isinstance(item, str):
            normalized.append({"name": item, "position": ""})
        elif isinstance(item, dict):
            normalized.append({
                "name": str(item.get("name", "")).strip(),
                "position": str(item.get("position", "")).strip(),
            })
    result["obstacles_detected"] = normalized
    result.setdefault("hamster_position", "")
    return result


# ─────────────────────────────────────────────────────────────
# 1-B단계: 자연어 행동 계획 생성  (Flash)
# ─────────────────────────────────────────────────────────────
async def generate_action_plan(
    base64_image: str,
    student_goal: str,
    obstacles: list,
    board_detected: bool = False,
    hamster_facing: str = "unknown",
    hamster_position: str = "",
    lang: str = "ko",
) -> dict[str, Any]:
    """
    학생이 입력한 목표와 사진 정보를 바탕으로
    행동 계획을 JSON으로 생성한다 (2~8단계, 목표 달성에 필요한 만큼).

    board_detected=True 이면 격자(칸) 단위 계획을 생성한다.

    반환 예시 (board_detected=False):
        {"steps": [
            {"step": 1, "action": "앞으로 20cm 이동", "detail": "장애물을 피해 직진해요."},
            {"step": 2, "action": "왼쪽으로 90도 회전", "detail": "책 옆을 돌아요."},
            {"step": 3, "action": "앞으로 15cm 이동", "detail": "목표 지점에 도착해요!"}
         ],
         "summary": "전체적으로 책을 피해서 목표에 도달하는 경로예요! 🗺️"}

    반환 예시 (board_detected=True):
        {"steps": [
            {"step": 1, "action": "앞으로 3칸 이동", "detail": "격자를 따라 직진해요."},
            {"step": 2, "action": "오른쪽으로 회전", "detail": "오른쪽 방향으로 돌아요."},
            {"step": 3, "action": "앞으로 2칸 이동", "detail": "목표 지점에 도착해요!"}
         ],
         "summary": "격자 위에서 목표 지점까지 이동하는 경로예요! 🗺️"}
    """
    # obstacles 는 [{name, position}] 또는 [str] 두 형식을 허용
    def _fmt_obs(item):
        if isinstance(item, dict):
            name = (item.get("name") or "").strip()
            pos = (item.get("position") or "").strip()
            return f"{name}({pos})" if pos else name
        return str(item)

    obstacles_str = ", ".join(_fmt_obs(o) for o in obstacles) if obstacles else "없음"
    hamster_pos_str = hamster_position.strip() or "사진에서 확인"

    direction_hint = (
        "## 방향 절대 원칙 (반드시 지킬 것)\n"
        "1) 햄스터봇 윗면 화살표 스티커가 가리키는 방향 = 봇의 '앞(정면)'이야.\n"
        "   장애물 위치 문자열에 적힌 '앞/뒤/왼쪽/오른쪽'은 **이미 이 화살표를 기준으로 한 봇 시점**이야.\n"
        "   사진의 위/아래/왼/오른 방향과는 무관하므로, 사진 프레임으로 다시 해석하지 마.\n"
        "2) 이동·회전 명령도 모두 봇 시점 기준이야:\n"
        "   - '앞으로 N칸/Ncm 이동' = 봇이 현재 바라보는 방향(화살표 방향)으로 전진\n"
        "   - '오른쪽으로 회전'      = 봇이 제자리에서 시계 방향 90도 회전 (화살표가 시계 방향으로 돌음)\n"
        "   - '왼쪽으로 회전'        = 봇이 제자리에서 시계 반대 방향 90도 회전\n"
        "3) 목표로 이동하는 표준 절차 (이 순서대로 추론):\n"
        "   (a) 목표물이 봇 기준 어느 방향인지 확인 (앞/뒤/왼쪽/오른쪽/앞왼쪽 등)\n"
        "   (b) 목표 방향으로 봇의 앞을 맞추기 위한 회전을 먼저 결정:\n"
        "       - 목표가 '바로 앞'이면 → 회전 없이 바로 전진\n"
        "       - 목표가 '오른쪽 옆'이면 → 오른쪽으로 회전\n"
        "       - 목표가 '왼쪽 옆'이면   → 왼쪽으로 회전\n"
        "       - 목표가 '바로 뒤'이면   → 오른쪽으로 회전을 2번(또는 왼쪽 2번)\n"
        "       - 목표가 '앞 왼쪽'이면   → 먼저 앞으로 몇 칸/cm 이동 후 왼쪽으로 회전, 다시 전진\n"
        "       - 목표가 '앞 오른쪽'이면 → 먼저 앞으로 몇 칸/cm 이동 후 오른쪽으로 회전, 다시 전진\n"
        "   (c) 회전 후에는 봇의 '앞'이 바뀐다는 점을 기억하며 다음 단계를 구성.\n"
        "4) '몸을 위쪽으로 돌린다'처럼 사진 프레임 어휘로 절대 생각하지 마.\n"
        "   항상 '봇의 앞을 목표 방향으로 맞춘다'라고 생각해.\n"
    )

    if board_detected:
        if lang == "en":
            movement_rules = (
                "## Definition of '1 cell' (very important)\n"
                "On the grid board, '1 cell' = the distance between two adjacent line "
                "intersections. The Hamster robot stands on intersections and moves "
                "intersection -> intersection. If an obstacle sits on intersection X, "
                "the robot must stop at the previous intersection.\n\n"
                "## Allowed actions (board / cell mode only)\n"
                "- Move forward N cells (N is a positive integer; use 'cells' only)\n"
                "- Move backward N cells\n"
                "- Turn right (90 degrees = once)\n"
                "- Turn left (90 degrees = once)\n\n"
                "## Notes\n"
                "- Before moving, verify that no obstacle sits on any intersection along the path\n"
                "- ALWAYS express distance in 'cells' (NEVER use cm in board mode)\n"
                "- For turns, write only the direction (no angle number, e.g. 'Turn right' OK, "
                "'Turn right 90 degrees' NOT OK)\n"
                "- action examples: 'Move forward 3 cells', 'Turn right', 'Move forward 2 cells'\n"
            )
            action_example = (
                '    {"step": 1, "action": "Move forward N cells OR turn left/right", '
                '"detail": "Friendly reason why we do this"},\n'
            )
        else:
            movement_rules = (
                "## 1칸의 정의 (매우 중요)\n"
                "격자판에서 '1칸' = 선이 만나는 교차점과 바로 이웃한 교차점 사이의 거리야.\n"
                "햄스터봇은 교차점에 서 있고, 이동 명령을 받으면 교차점 → 교차점 단위로 움직여.\n"
                "장애물이 교차점 X에 놓여 있으면, 봇이 X에 도달하기 전 교차점에서 멈춰야 해.\n"
                "즉, 봇의 현재 교차점에서 장애물 교차점까지의 거리가 2칸이면 최대 1칸만 이동 가능해.\n\n"
                "## 햄스터봇이 할 수 있는 행동 (격자 모드 - 이것만 사용)\n"
                "- 앞으로 N칸 이동 (N은 1 이상의 정수, '칸' 단위만 사용)\n"
                "- 뒤로 N칸 이동\n"
                "- 오른쪽으로 회전 (90도 = 1회)\n"
                "- 왼쪽으로 회전 (90도 = 1회)\n\n"
                "## 주의사항\n"
                "- 이동 전에 반드시 경로상 모든 교차점에 장애물이 없는지 확인해\n"
                "- 거리는 반드시 '칸' 단위로만 표현해 (cm 절대 금지)\n"
                "- 회전은 방향만 적어 (각도 숫자 금지, 예: '오른쪽으로 회전' O / '오른쪽으로 90도 회전' X)\n"
                "- action 예시: '앞으로 3칸 이동', '오른쪽으로 회전', '앞으로 2칸 이동'\n"
            )
            action_example = (
                '    {"step": 1, "action": "앞으로 N칸 이동 또는 방향 회전", "detail": "왜 이렇게 하는지 친절한 이유"},\n'
            )
    else:
        if lang == "en":
            movement_rules = (
                "## Allowed actions (use ONLY these)\n"
                "- Move forward (distance in cm)\n"
                "- Move backward (distance in cm)\n"
                "- Turn left / right (angle in degrees)\n\n"
                "## Notes\n"
                "- Always include a concrete number with the cm unit\n"
                "- action examples: 'Move forward 20cm', 'Turn left 90 degrees'\n"
            )
            action_example = (
                '    {"step": 1, "action": "Short action description with cm/degree units", '
                '"detail": "Friendly reason why we do this"},\n'
            )
        else:
            movement_rules = (
                "## 햄스터봇이 할 수 있는 행동 (이것만 사용)\n"
                "- 앞으로 이동 (거리: cm 단위)\n"
                "- 뒤로 이동 (거리: cm 단위)\n"
                "- 왼쪽/오른쪽으로 회전 (각도: 도 단위)\n\n"
                "## 주의사항\n"
                "- 거리는 반드시 cm 단위로 구체적인 숫자를 포함해\n"
                "- action 예시: '앞으로 20cm 이동', '왼쪽으로 90도 회전'\n"
            )
            action_example = (
                '    {"step": 1, "action": "짧은 행동 설명 (cm·도 단위 포함)", "detail": "왜 이렇게 하는지 친절한 이유"},\n'
            )

    board_boundary_rule = ""
    if board_detected:
        board_boundary_rule = (
            "## 발판(말판) 경계 절대 원칙\n"
            "햄스터봇이 올라가 있는 발판(격자 보드)이 사진 아래에 있어. 햄스터봇은 절대로 이 발판 밖으로 나가서는 안 돼.\n"
            "모든 이동·회전 단계를 합쳐도 햄스터봇이 발판의 어느 모서리도 넘어가지 않도록 칸 수와 방향을 신중하게 정해.\n"
            "발판 끝에 가까이 있으면 그 방향으로 더 이동시키지 말고, 회전부터 시켜서 발판 안쪽으로 향하게 해.\n"
            "목표가 발판 밖에 있더라도 발판 안쪽 가장 가까운 칸에서 멈춰. 발판 밖으로 나가지 않는 것이 목표 도달보다 우선이야.\n\n"
        )

    facing_note_map = {
        "toward_camera": "화살표가 카메라 쪽을 향함 (봇의 앞이 사진 아래 또는 관찰자 쪽)",
        "away_from_camera": "화살표가 카메라 반대 방향을 향함 (봇의 앞이 사진 위 또는 먼 쪽)",
        "left": "화살표가 사진 왼쪽을 가리킴 (봇의 앞 = 사진 왼쪽)",
        "right": "화살표가 사진 오른쪽을 가리킴 (봇의 앞 = 사진 오른쪽)",
        "up": "화살표가 사진 위쪽을 가리킴 (봇의 앞 = 사진 위쪽)",
        "down": "화살표가 사진 아래쪽을 가리킴 (봇의 앞 = 사진 아래쪽)",
        "unknown": "화살표 방향 불확실 — 장애물 위치 문자열(봇 시점)을 그대로 신뢰할 것",
    }
    facing_note = facing_note_map.get(hamster_facing, facing_note_map["unknown"])

    lang_directive = ""
    if lang == "en":
        lang_directive = (
            "## LANGUAGE REQUIREMENT (override any other language hint)\n"
            "All natural-language fields in the JSON output (every step's 'action' and 'detail', "
            "and the 'summary') MUST be written in clear, friendly English suitable for an "
            "elementary school student. Do not use Korean for these fields. "
            "Use units like 'cm' or 'cells' (for board mode) and clear directions like "
            "'forward', 'backward', 'turn left', 'turn right'. No emojis.\n\n"
        )
    prompt = (
        f"{lang_directive}"
        f'학생의 목표: "{student_goal}"\n'
        f"햄스터봇 현재 위치: {hamster_pos_str}\n"
        f"햄스터봇 화살표 방향(참고): {facing_note}\n"
        f"사진에서 발견된 장애물(햄스터봇 기준 위치 포함): {obstacles_str}\n\n"
        f"{direction_hint}\n"
        f"{board_boundary_rule}"
        "## [1단계] 관련성 판단\n"
        "학생의 목표가 햄스터봇의 이동·회전·목적지 도달과 관련이 있는지 먼저 판단해.\n"
        "관련 없는 입력 예시: 날씨 질문, 노래 가사, 무의미한 문자, 로봇과 무관한 이야기 등.\n"
        "관련 없다고 판단하면 irrelevant=true 를 반환하고 steps 는 빈 배열로 둬.\n\n"
        "## [2단계] 행동 계획 (관련 있는 경우만)\n"
        f"{movement_rules}\n"
        "## 절대 금지 행동 (햄스터봇은 불가능)\n"
        "- 물체를 밀거나 치우기\n"
        "- 물체를 집거나 들기\n"
        "- 장애물을 옮기거나 넘기\n\n"
        "장애물이 있으면 반드시 '피해서' 돌아가는 경로를 계획해.\n"
        "## 장애물 우회 전략 (매우 중요)\n"
        "목표가 봇의 앞 왼쪽/앞 오른쪽에 있고 가는 길에 장애물이 있을 때,\n"
        "절대로 '먼저 회전해서 목표 방향을 향한다' 는 방식으로 계획하지 마.\n"
        "그 방식은 장애물을 통과하게 되거나 발판 밖으로 나가기 쉬워.\n"
        "올바른 우회 전략:\n"
        "  [전략 A] 앞으로 먼저 충분히 직진 → 장애물의 열/행을 완전히 지나친 뒤 → 회전 → 목표로 직진\n"
        "  [전략 B] 옆으로(왼/오) 먼저 이동해 장애물의 행/열을 피한 뒤 → 앞으로 직진\n"
        "전략을 선택하기 전에, 머릿속으로 각 이동 후 봇 위치를 시뮬레이션해서\n"
        "경로상 어느 칸도 장애물 위치와 겹치지 않는지 확인해.\n"
        "각 단계의 detail 에는 어떤 장애물을 어느 방향(햄스터봇 기준)으로 피하는지, 또는 목표 지점이 햄스터봇 기준 어느 방향에 있어서 그렇게 움직이는지 짧게 적어 줘.\n"
        "이동과 회전만으로 목표를 달성하는 행동 계획을 JSON으로 만들어 줘.\n"
        "단계 수는 목표를 완성하는 데 필요한 만큼 자유롭게 써 (최소 2단계, 최대 8단계).\n"
        "목표 지점에 실제로 도착하는 마지막 이동 단계까지 반드시 포함해.\n"
        "반드시 JSON 형식으로만 대답해. 마크다운 코드블록 없이 순수 JSON만 출력해.\n"
        "모든 텍스트(action, detail, summary)에 이모지(이모티콘)를 절대 사용하지 마.\n\n"
        "JSON 스키마:\n"
        "{\n"
        '  "irrelevant": false,\n'
        '  "steps": [\n'
        f"{action_example}"
        '    {"step": 2, "action": "...", "detail": "..."},\n'
        '    {"step": N, "action": "...", "detail": "..."}\n'
        "  ],\n"
        '  "summary": "전체 계획 요약 (1~2문장)"\n'
        "}\n\n"
        "관련 없는 입력일 때 반환 예시:\n"
        '{"irrelevant": true, "steps": [], "summary": ""}'
        + (
            "\n\n## FINAL LANGUAGE OVERRIDE\n"
            "Any Korean text you saw in this prompt above is reference scaffolding only. "
            "EVERY natural-language field you OUTPUT (each step's 'action', each step's "
            "'detail', and 'summary') MUST be written in natural English. Do not produce "
            "any Korean characters in these output fields.\n"
            if lang == "en" else ""
        )
    )

    image = _image_part_inline(base64_image)

    if _is_claude_model(settings.PLAN_MODEL):
        raw_text = await _generate_plan_claude(prompt, lang=lang)
    else:
        response = await _generate(
            model=settings.PLAN_MODEL,
            fallback=_FLASH_FALLBACK,
            contents=[image, prompt],
            config=_plan_config(lang),
        )
        raw_text = response.text

    result = _extract_json(raw_text)

    if result.get("irrelevant"):
        return {"irrelevant": True}

    # steps가 유효하지 않으면 단순화된 프롬프트로 1회 재시도
    if not isinstance(result.get("steps"), list) or len(result["steps"]) == 0:
        logger.warning(f"계획 생성 실패 (1차). 재시도. raw 시작: {raw_text[:80]!r}")
        retry_prompt = (
            f"{lang_directive}"
            f'학생의 목표: "{student_goal}"\n'
            f"사진에서 발견된 장애물: {obstacles_str}\n\n"
            "햄스터봇이 이동과 회전만으로 목표를 달성하는 계획을 JSON으로 만들어 줘.\n"
            "목표 지점에 실제로 도착하는 마지막 이동까지 모두 포함해 (2~8단계).\n"
            "반드시 아래 JSON 형식만 출력해:\n"
            "{\n"
            '  "steps": [\n'
            '    {"step": 1, "action": "행동 설명", "detail": "이유"},\n'
            '    {"step": 2, "action": "행동 설명", "detail": "이유"},\n'
            '    {"step": N, "action": "행동 설명", "detail": "이유"}\n'
            "  ],\n"
            '  "summary": "전체 요약"\n'
            "}"
        )
        if _is_claude_model(settings.PLAN_MODEL):
            retry_raw = await _generate_plan_claude(retry_prompt, lang=lang)
        else:
            retry_response = await _generate(
                model=settings.PLAN_MODEL,
                fallback=_FLASH_FALLBACK,
                contents=[image, retry_prompt],
                config=_plan_config(lang),
            )
            retry_raw = retry_response.text
        result = _extract_json(retry_raw)

    if not isinstance(result.get("steps"), list) or len(result["steps"]) == 0:
        err_msg = (
            "The AI couldn't make a plan. Want to enter the goal again?"
            if lang == "en"
            else "AI가 계획을 만들지 못했어요. 목표를 다시 입력해 볼까요?"
        )
        return {"error": err_msg}
    return result


# ─────────────────────────────────────────────────────────────
# 3단계: Vibe-Explanation + 파이썬 코드 생성  (Pro + RAG)
# ─────────────────────────────────────────────────────────────
async def generate_python_code(
    action_plan: dict[str, Any],
    student_choice: int,
    platform: str = "entry",
    rag_context: str = "",   # 비어있으면 내부에서 RAG 자동 검색
    board_detected: bool = False,
    student_goal: str = "",
    hamster_position: str = "",
    obstacles: list | None = None,
    lang: str = "ko",
) -> dict[str, Any]:
    """
    학생이 선택한 옵션과 행동 계획을 반영해
    햄스터봇 파이썬 코드 + 선생님 설명을 생성한다.

    student_choice:
        1 = 이대로 실행하기
        2 = 더 안전하게 (속도 감소)
        3 = 다시 계획 생성하기 (라우터에서 처리, 여기선 호출 안 됨)
        4 = 장애물 회피 우선
        5 = 더 효율적으로 (최단경로)
    """
    if board_detected:
        safer_instruction = (
            "[중요] 말판(격자 보드)이 감지되었으므로 반드시 보드 명령어"
            "(`Hamster.board_forward()`, `Hamster.board_turn()`, `Hamster.move_forward()`)를 "
            "그대로 사용해야 해. 보드 명령은 블로킹 명령이라 velocity 파라미터가 없으니, "
            "안전하게 만들기 위해서는 파일 상단의 `SPEED` 상수 값만 20 이하로 낮춰. "
            "이동 방식 자체를 set_wheels + time.sleep으로 바꾸지 마. "
            "보드 명령어 사용은 그대로 유지하고 SPEED 상수만 줄여서 천천히 움직이도록 해."
        )
        faster_instruction = (
            "[중요] 말판(격자 보드)이 감지되었으므로 보드 명령어를 그대로 사용해야 해. "
            "이동 방식을 set_wheels + time.sleep으로 바꾸지 말고, "
            "보드 명령어(`board_forward`, `board_turn`, `move_forward`)를 유지한 채 "
            "불필요한 회전과 이동을 줄여서 최단 경로로 최적화해 줘. "
            "연속된 같은 방향 이동은 `move_forward(N)` 한 번으로 합치는 것을 우선 고려해."
        )
    else:
        safer_instruction = (
            "모든 이동의 velocity 파라미터를 20 이하로 낮춰서 안전하게 구현해 줘. "
            "기본 속도(velocity 생략 시 30%)보다 더 느리게 설정해."
        )
        faster_instruction = (
            "불필요한 회전과 이동을 줄여서 최단 경로로 최적화해 줘. "
            "연속된 같은 방향 이동은 합쳐서 한 번에 처리해."
        )

    choice_context = {
        1: "원래 계획 그대로 구현해 줘.",
        2: safer_instruction,
        4: (
            "[절대 원칙] 사진(1단계 이미지 분석 결과)에 보이는 장애물 위치를 기준으로, "
            "햄스터봇이 장애물과 근접하여 부딪힐 가능성이 있으면 목표 도달보다 회피를 더 우선해. "
            "근접 센서나 실시간 거리 측정 코드를 사용하지 말고, 사진에서 파악한 장애물 위치 정보만 가지고 "
            "경로상 충돌이 예상되는 구간에서는 한 칸 더 우회하거나 더 일찍 회전하는 식으로 여유를 두고 안전한 경로로 계획해. "
            "장애물로 인해 목표에 도달할 수 없으면 최대한 근접한 안전한 위치에서 멈춰야 해."
        ),
        5: faster_instruction,
    }.get(student_choice, "원래 계획 그대로 구현해 줘.")

    # ── RAG 검색: 행동 계획을 쿼리로 관련 API 문서 검색 ─────
    if not rag_context:
        plan_summary = action_plan.get("summary", "")
        plan_steps = " ".join(
            s.get("action", "") for s in action_plan.get("steps", [])
        )
        rag_query = f"{plan_summary} {plan_steps}".strip() or "햄스터봇 이동 코드"
        if student_choice == 4:
            rag_query = f"장애물 회피 우회 경로 안전 마진 {rag_query}"

        try:
            rag_context = rag_service.search(rag_query, top_k=5, platform=platform)
            logger.debug(f"RAG 검색 완료: query='{rag_query[:50]}'")
        except Exception as e:
            logger.warning(f"RAG 검색 실패, 폴백 사용: {e}")
            rag_context = ""

    plan_json = json.dumps(action_plan, ensure_ascii=False, indent=2)

    board_note = (
        "말판(격자 보드) 감지: 있음 → `move_forward(n)`, `board_turn()` 사용 가능"
        if board_detected else
        "말판(격자 보드) 감지: 없음 → `set_wheels()` + `time.sleep()` 방식 필수 사용"
    )

    # 1단계 이미지 분석 컨텍스트 (3단계 설명에 사용)
    def _fmt_obs2(item):
        if isinstance(item, dict):
            name = (item.get("name") or "").strip()
            pos = (item.get("position") or "").strip()
            return f"{name}({pos})" if pos else name
        return str(item)

    obstacles = obstacles or []
    obstacles_ctx = ", ".join(_fmt_obs2(o) for o in obstacles) if obstacles else "없음"
    analysis_ctx = (
        "## 1단계 이미지 분석 결과 (설명에 반드시 활용)\n"
        f"- 학생이 입력한 목표: {student_goal or '(없음)'}\n"
        f"- 햄스터봇 현재 위치: {hamster_position or '사진에서 확인'}\n"
        f"- 사진에서 발견된 장애물(햄스터봇 기준): {obstacles_ctx}\n"
    )

    if platform == "robomation":
        platform_rules = (
            f"{ROBOMATION_WIKI_DIRECTIVE}\n"
            "## 절대 규칙 (반드시 지킬 것 - 로보메이션 랩 전용)\n"
            "- 반드시 `import asyncio` 로 시작\n"
            "- 한 번 실행할 이동 코드는 `async def setup():` 함수 안에 작성\n"
            "- `def loop():` 는 반복 실행 코드용 (단순 이동이면 `return` 만)\n"
            "- 바퀴 속도 설정: `__('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 속도)`\n"
            "  속도 범위: -100 ~ 100 (양수=전진, 음수=후진)\n"
            "- LED 설정: `__('HamsterS*0:led.left').d = [R, G, B]`\n"
            "- 대기: `await asyncio.sleep(초)` (setup 함수 안에서만)\n"
            "- 정지: 양쪽 바퀴 속도를 0으로 설정\n\n"
            "## 코드 형식 예시\n"
            "import asyncio\n\n"
            "async def setup():\n"
            "    # 전진 1초\n"
            "    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 50)\n"
            "    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 50)\n"
            "    await asyncio.sleep(1)\n"
            "    # 정지\n"
            "    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 0)\n"
            "    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 0)\n"
            "    return\n\n"
            "def loop():\n"
            "    return\n"
        )
        platform_editor = "로보메이션 랩"
        code_template = (
            '"import asyncio\\n\\nasync def setup():\\n    # 이동 코드\\n    return\\n\\ndef loop():\\n    return\\n"'
        )
    else:
        if board_detected:
            movement_rules = (
                "### ✅ 말판(격자 보드) 있음 → 보드 명령어 사용\n"
                "  Hamster.board_forward()       — 앞으로 1칸 이동 (IR 마커 1개) ★기본★\n"
                "  Hamster.move_forward(칸수)    — 말판 N칸 전진 (한 번에 N칸)\n"
                "  Hamster.move_backward(칸수)   — 말판 N칸 후진\n"
                "  Hamster.board_turn('LEFT')    — 말판 기준 왼쪽 90도 회전\n"
                "  Hamster.board_turn('RIGHT')   — 말판 기준 오른쪽 90도 회전\n"
                "  Hamster.turn('LEFT', 횟수)    — 왼쪽으로 N×90도 회전 (2=180도)\n"
                "  → import time 불필요, 블로킹 명령이라 자동 정지됨\n\n"
                "## 필수 코드 구조 (말판 모드 표준 템플릿)\n"
                "  1) `import Entry` + `import Hamster` 두 줄만 (import time 불필요)\n"
                "  2) 파일 상단에 반드시 `SPEED = 30`, `FWD_10CM = 0.85`, `TURN_90 = 0.55` 상수 3줄 선언\n"
                "     (보드 명령이 주력이지만 상수는 표준 템플릿이므로 항상 포함)\n"
                "  3) `def when_start():` 안에서 이동은 **`Hamster.board_forward()` 를 반복 호출하는 것을 최우선 권장**\n"
                "     (N칸 이동 = board_forward() × N번 호출 — 매 칸 IR 재정렬로 정확도↑)\n"
                "  4) `move_forward(N)` 사용 가능하나 누적 오차 가능성으로 board_forward 반복이 더 안정적\n"
                "  5) 회전은 항상 `Hamster.board_turn(\"LEFT\")` / `Hamster.board_turn(\"RIGHT\")`\n"
            )
            code_template = (
                '"import Entry\\nimport Hamster\\n\\n\\nSPEED = 30\\nFWD_10CM = 0.85\\nTURN_90 = 0.55\\n\\ndef when_start():\\n    Hamster.board_forward()\\n    Hamster.board_turn(\\"RIGHT\\")\\n    Hamster.board_forward()\\n    Hamster.board_forward()\\n    Hamster.board_turn(\\"LEFT\\")\\n    Hamster.board_forward()\\n"'
            )
        else:
            movement_rules = (
                "### ⚠️ 말판(격자 보드) 없음 → set_wheels + time.sleep 방식 필수\n"
                "  - `import time` 을 반드시 세 번째 줄에 추가\n"
                "  - board_turn(), move_forward(n) 절대 사용 금지 (말판 없으면 오작동)\n"
                "  - 이동/회전을 모두 아래 패턴으로 구현:\n\n"
                "  SPEED = 30          # 속도 (1~100)\n"
                "  FWD_10CM = 0.85     # 속도30으로 10cm 이동 시간(초)\n"
                "  TURN_90  = 0.55     # 속도30으로 90도 회전 시간(초)\n\n"
                "  # 전진 N×10cm:\n"
                "  Hamster.set_wheels(SPEED, SPEED)\n"
                "  time.sleep(FWD_10CM * N)\n"
                "  Hamster.set_wheels(0, 0)\n\n"
                "  # 왼쪽 90도 회전:\n"
                "  Hamster.set_wheels(-SPEED, SPEED)\n"
                "  time.sleep(TURN_90)\n"
                "  Hamster.set_wheels(0, 0)\n\n"
                "  # 오른쪽 90도 회전:\n"
                "  Hamster.set_wheels(SPEED, -SPEED)\n"
                "  time.sleep(TURN_90)\n"
                "  Hamster.set_wheels(0, 0)\n"
            )
            code_template = (
                '"import Entry\\nimport Hamster\\nimport time\\n\\nSPEED = 30\\nFWD_10CM = 0.85\\nTURN_90 = 0.55\\n\\ndef when_start():\\n    Hamster.set_wheels(SPEED, SPEED)\\n    time.sleep(FWD_10CM * 2)\\n    Hamster.set_wheels(0, 0)\\n"'
            )

        platform_rules = (
            "## 절대 규칙 (반드시 지킬 것 - 엔트리 파이썬 전용)\n"
            "- 반드시 `import Entry` 와 `import Hamster` 두 줄로 임포트\n"
            + ("- 말판 없을 때: `import time` 세 번째 줄 추가 필수\n" if not board_detected else "")
            + "- 모든 코드는 반드시 `def when_start():` 함수 안에 작성\n"
            "- API 호출은 `Hamster.메서드()` 형태 (인스턴스 생성 금지)\n"
            "- `try/finally` 구조 금지, `dispose()` 호출 금지\n\n"
            f"{movement_rules}\n"
            "## 공통 API (말판 유무 무관)\n"
            "  Hamster.set_wheels(왼쪽, 오른쪽) — 바퀴 속도 설정 (-100~100)\n"
            "  Hamster.set_led_green('BOTH')    — 초록 LED\n"
            "  Hamster.set_led_red('BOTH')      — 빨간 LED\n"
            "  Hamster.beep()                   — 소리\n"
        )
        platform_editor = "엔트리 파이썬 에디터"

    rag_header = (
        "## 햄스터-S API 레퍼런스 (RobomationLAB 공식 위키 발췌)\n"
        "출처: https://github.com/RobomationLAB/User_Guide/\n"
        "아래 내용은 유일한 진실 원본이며, 여기에 없는 함수/문법은 절대 사용 금지.\n"
        if platform == "robomation" else
        "## 햄스터-S API 레퍼런스 (공식 문서 발췌)\n"
    )
    lang_directive = ""
    if lang == "en":
        lang_directive = (
            "## LANGUAGE REQUIREMENT (override any other language hint)\n"
            "All natural-language string fields in the JSON output ('change_reason', "
            "'explanation', and every modified step's 'action' and 'detail') MUST be written "
            "in clear, friendly English suitable for an elementary school student. "
            "Code comments inside 'python_code' MUST also be in English. "
            "Keep Python keywords, API names, and string literals like 'LEFT'/'RIGHT' as-is.\n\n"
        )
    code_comment_lang_note = (
        "code comments in English"
        if lang == "en"
        else "한국어 주석 포함, 주석에도 이모지 금지"
    )
    prompt = (
        f"{lang_directive}"
        f"{rag_header}"
        f"{rag_context}\n\n"
        f"{board_note}\n\n"
        f"{platform_rules}\n\n"
        f"{analysis_ctx}\n"
        f"## 학생의 행동 계획\n{plan_json}\n\n"
        f"## 구현 지침\n{choice_context}\n\n"
        "위 내용을 바탕으로 네 가지를 JSON으로 작성해 줘.\n"
        "모든 텍스트(change_reason, explanation, 코드 주석)에는 이모지(이모티콘)를 절대 사용하지 마.\n\n"
        "1. plan_changed: 구현 지침을 반영하면서 이동 경로나 단계 순서가 실질적으로 바뀌었으면 true,\n"
        "   속도/센서 코드만 달라지고 이동 경로는 그대로면 false\n"
        "2. change_reason: 계획이 바뀐 이유 또는 안 바뀐 이유를 초등학생 말투로 1~2문장 (이모지 금지)\n"
        + (
            "   - plan_changed=false example: 'The path stays the same, but I lowered the speed so it moves more safely.'\n"
            "   - plan_changed=true  example: 'I removed an unnecessary turn so the route is faster.'\n"
            if lang == "en" else
            "   - plan_changed=false 예시: '이동 경로는 그대로지만 속도를 낮춰서 더 안전하게 만들었어요.'\n"
            "   - plan_changed=true  예시: '불필요한 회전을 줄여서 더 빠른 경로로 바꿨어요.'\n"
        )
        + "3. modified_steps: plan_changed=true일 때만 바뀐 계획 단계 배열 (아래 형식), false면 빈 배열 []\n"
        "4. explanation: 초등학생 선생님 말투로 아래 내용을 모두 포함해서 자세하게 설명 (6~10문장, 이모지 금지)\n"
        + (
            "   (1) Start by quoting the Stage 1 image analysis. Example: 'Because the hair clip is "
            "in the front-right of the hamster robot, I told it to move forward first and then turn "
            "right toward the hair clip.'\n"
            "       -> Mention the student's goal (target object name), the robot's current position, "
            "and obstacle positions (relative to the robot) naturally.\n"
            "   (2) Which command style you chose based on whether a board was detected\n"
            "   (3) Why each movement/rotation uses the specific number (cells, time, speed) it does\n"
            "   (4) How the student's chosen option is reflected in the code\n"
            "   (5) Step-by-step description of how the code runs in order\n"
            "   (6) Friendly description of how the real robot will move\n"
            if lang == "en" else
            "   ① 1단계 이미지 분석 결과를 반드시 인용하면서 시작해. 예: '목표물인 머리핀이 햄스터봇 기준 왼쪽 위에 있기 때문에, 먼저 왼쪽으로 회전한 다음 전진 명령을 반복하도록 했답니다.'\n"
            "      → 학생의 목표(목표물 이름), 햄스터봇 현재 위치, 장애물 위치(햄스터봇 기준 방향)를 자연스럽게 언급해야 함\n"
            "   ② 말판이 있었는지/없었는지에 따라 어떤 명령어 방식을 선택했는지\n"
            "   ③ 각 이동/회전 명령에서 숫자(칸수, 시간, 속도)를 왜 그렇게 정했는지\n"
            "   ④ 학생이 선택한 옵션이 코드에 어떻게 반영되었는지\n"
            "   ⑤ 코드가 순서대로 어떻게 실행되는지 단계별로 설명\n"
            "   ⑥ 실제 로봇이 어떻게 움직일지 친절하게 설명\n"
        )
        f"5. python_code: 바로 복사해서 {platform_editor}에 붙여넣을 수 있는 완전한 코드 ({code_comment_lang_note})\n\n"
        "반드시 JSON 형식으로만 대답해. 코드 안의 따옴표는 이스케이프해.\n\n"
        "JSON 스키마:\n"
        "{\n"
        '  "plan_changed": false,\n'
        '  "change_reason": "이유 설명...",\n'
        '  "modified_steps": [],\n'
        '  "explanation": "선생님 말투 자세한 설명...",\n'
        f'  "python_code": {code_template}\n'
        "}"
        + (
            "\n\n## FINAL LANGUAGE OVERRIDE\n"
            "Any Korean text in this prompt above is reference scaffolding only. EVERY "
            "natural-language field you OUTPUT (the 'change_reason', 'explanation', and "
            "every modified step's 'action' and 'detail') MUST be written in natural English. "
            "Code comments inside 'python_code' MUST also be in English. Do NOT produce any "
            "Korean characters in these output fields. Python keywords, API names, and string "
            "literals like 'LEFT'/'RIGHT' stay as-is.\n"
            if lang == "en" else ""
        )
    )

    response = await _generate(
        model=settings.FLASH_MODEL,
        fallback=_FLASH_FALLBACK,
        contents=prompt,
        config=_code_config(lang),
    )
    result = _extract_json(response.text)

    # 플랫폼별 자동 교정
    if "python_code" in result and isinstance(result["python_code"], str):
        code = result["python_code"]
        if platform == "entry":
            code = code.replace("from roboid import *", "import Entry\nimport Hamster")
            code = code.replace("from hamster import *", "import Entry\nimport Hamster")
            code = code.replace("import HamsterS", "import Hamster")
            code = code.replace("HamsterS.", "Hamster.")
            code = code.replace("hamster = HamsterS()", "")
            code = code.replace("hamster = Hamster()", "")
        result["python_code"] = code

    return result
