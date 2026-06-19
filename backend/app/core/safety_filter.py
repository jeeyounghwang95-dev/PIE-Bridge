# backend/app/core/safety_filter.py
#
# PIE BRIDGE - 안전 필터 (Safety Guardrails)
#
# 위험 키워드 / 욕설(한국어 + 영어) 감지 시:
#   - 파이썬 코드 생성 차단
#   - safety_logs DB에 기록 (ai_routes.py 에서 호출)
#   - 친절한 경고 메시지 반환 (UI 언어에 맞춰 ko/en)
#
# 욕설 목록:
#   - profanity_ko.txt : 한국어 (부분 문자열 매칭)
#   - profanity_en.txt : 영어   (단어 경계 매칭 + 리트스피크 정규화)
#   목록 갱신 시 해당 txt 만 수정하면 됨 (서버 재시작 필요)
#
# ⚠️ 학생이 자유롭게 텍스트를 입력할 수 있는 모든 경로(목표 입력,
#    수정 제안하기의 문제점/제안 칸 등)에서 반드시 check() 를 거쳐야 한다.

import re
from pathlib import Path


# ── 위험 행동 키워드 (한국어 — 부분 문자열 매칭) ──────────────
_DANGER_SPEED_KO = [
    "전속력", "최고속도", "최고 속도", "최대속도", "최대 속도", "풀 속도", "풀속도",
    "100% 속도", "100%속도", "제일 빠르게", "가장 빠르게", "최대한 빠르게",
]

_DANGER_ACTION_KO = [
    "떨어뜨려", "떨어트려", "떨어져", "충돌", "들이받", "부숴", "부수", "파괴",
    "망가뜨려", "망가트려", "밀어버려", "밀어", "때려", "공격", "박아", "처박",
]

# ── 위험 행동 키워드 (영어 — 단어 경계 매칭) ──────────────────
_DANGER_SPEED_EN = [
    "full speed", "max speed", "maximum speed", "top speed", "full throttle",
    "fastest", "100% speed", "as fast as possible",
]

_DANGER_ACTION_EN = [
    "crash", "smash", "destroy", "break it", "knock over", "knock down",
    "push it", "shove", "hit it", "attack", "ram", "ram into", "topple",
    "wreck", "run over", "run into", "drop it",
]


# ── 욕설 목록: txt 에서 로드 ─────────────────────────────────
def _load_words(path: Path) -> list[str]:
    """txt 파일에서 단어를 읽어 반환. # 주석·빈 줄 무시."""
    if not path.exists():
        return []
    words = []
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.split("#")[0].strip()
        if word:
            words.append(word.lower())
    return words


_CORE_DIR = Path(__file__).parent
_PROFANITY_KO = _load_words(_CORE_DIR / "profanity_ko.txt")
_PROFANITY_EN = _load_words(_CORE_DIR / "profanity_en.txt")

# 매칭 방식별 분류:
#   - 부분 문자열(substring): 한국어 (띄어쓰기/조사 변형이 많고 \b 가 의미 없음)
#   - 단어 경계(word-boundary): 영어 (substring 으로 하면 class/pass 등 오탐 발생)
_SUBSTRING_TERMS = _DANGER_SPEED_KO + _DANGER_ACTION_KO + _PROFANITY_KO
_WORDBOUNDARY_TERMS = _DANGER_SPEED_EN + _DANGER_ACTION_EN + _PROFANITY_EN

# 카테고리 판정용 집합 (소문자 기준)
_SET_DANGER_SPEED = {w.lower() for w in (_DANGER_SPEED_KO + _DANGER_SPEED_EN)}
_SET_DANGER_ACTION = {w.lower() for w in (_DANGER_ACTION_KO + _DANGER_ACTION_EN)}

# ── 리트스피크 정규화 (영어 우회 표기 차단) ───────────────────
#   f*ck / sh1t / @ss / fuuuck 등을 잡기 위해 영어 매칭 전 텍스트를 정규화.
_LEET_MAP = str.maketrans({
    "@": "a", "4": "a",
    "$": "s", "5": "s",
    "0": "o",
    "1": "i", "!": "i",
    "3": "e",
    "7": "t",
    "8": "b",
    "+": "t",
})


def _normalize_for_en(text: str) -> str:
    """영어 욕설 매칭용 정규화: 소문자화 → 숫자 리트 치환 → 알파벳 반복 축약."""
    lowered = text.lower().translate(_LEET_MAP)
    # "fuuuck", "shiiit" 처럼 늘려 쓴 표기 축약 (같은 '글자' 3회 이상 → 1회).
    # 마스킹 기호 반복(f*** 의 ***)은 글자가 아니므로 축약하지 않는다.
    return re.sub(r"([a-z])\1{2,}", r"\1", lowered)


# 글자를 가리는 마스킹 기호 (f*ck, f**k, sh#t, a** 등)
_MASK_CHARS = "*#"


def _term_to_tolerant_regex(term: str) -> str:
    """
    영어 금지어 한 개를 우회 표기에 강한 정규식 조각으로 변환.
    - 글자 사이에 구두점/공백 등 비단어문자가 끼어도 매칭 (f.u.c.k, f u c k)
    - 토큰의 '첫 글자'는 그대로 두어 앵커로 삼고(오탐 방지),
      그 뒤 글자들은 마스킹 기호(* #)로 대체돼도 매칭 (f*ck, f**k, sh#t, a**hole)
    - 구(공백 포함)는 공백 위치에 최소 1개의 구분자를 요구
    - 숫자/단어 경계 lookaround 와 함께 쓰여 class/pass/Scunthorpe 같은 오탐을 막는다.
    """
    pieces: list[str] = []
    prev_was_letter = False
    at_token_start = True
    for ch in term:
        if ch == " ":
            pieces.append(r"[\W_]+")
            prev_was_letter = False
            at_token_start = True
            continue
        if prev_was_letter:
            pieces.append(r"[\W_]{0,3}")
        if at_token_start:
            # 토큰 첫 글자는 마스킹 불가 (실제 글자/리트만) — 매칭 앵커
            pieces.append(re.escape(ch))
        else:
            # 첫 글자 뒤로는 마스킹 기호로 가려져도 매칭
            pieces.append("[" + re.escape(ch) + re.escape(_MASK_CHARS) + "]")
        prev_was_letter = True
        at_token_start = False
    return "".join(pieces)


class SafetyFilter:
    """
    입력 텍스트에서 위험 키워드 / 욕설(한국어·영어)을 감지한다.

    사용법:
        result = safety_filter.check("전속력으로 앞으로 가줘", lang="ko")
        # result → {"blocked": True, "reason": "danger_speed", "matched": "...", "message": "..."}
    """

    def __init__(
        self,
        substring_terms: list[str],
        wordboundary_terms: list[str],
    ) -> None:
        # 한국어 등: 부분 문자열 매칭 (대소문자 무시)
        sub_patterns = [re.escape(w) for w in substring_terms if w]
        self._sub_pattern = (
            re.compile("|".join(sub_patterns), re.IGNORECASE) if sub_patterns else None
        )
        # 영어: 단어 경계 매칭 (정규화된 텍스트에 적용)
        #   - 우회 표기에 강한 정규식으로 변환 (f*ck, sh1t, f u c k 등)
        #   - 긴 구문이 먼저 매칭되도록 길이 내림차순 정렬
        #   - 앞뒤 lookaround 로 단어 경계를 둬서 class/pass 등 오탐 방지
        wb_sorted = sorted({w for w in wordboundary_terms if w}, key=len, reverse=True)
        wb_patterns = [_term_to_tolerant_regex(w) for w in wb_sorted]
        self._wb_pattern = (
            re.compile(r"(?<![a-z0-9])(?:" + "|".join(wb_patterns) + r")(?![a-z0-9])")
            if wb_patterns else None
        )

    @staticmethod
    def _categorize(word: str) -> str:
        w = word.lower()
        if w in _SET_DANGER_SPEED:
            return "danger_speed"
        if w in _SET_DANGER_ACTION:
            return "danger_action"
        return "profanity"

    def check(self, text: str, lang: str = "ko") -> dict:
        """
        Returns:
            {"blocked": False}
            또는
            {"blocked": True, "reason": str, "matched": str, "message": str}
        """
        if not text:
            return {"blocked": False}

        # 1) 한국어/부분 문자열 매칭
        if self._sub_pattern:
            m = self._sub_pattern.search(text)
            if m:
                matched = m.group(0)
                reason = self._categorize(matched)
                return {
                    "blocked": True,
                    "reason": reason,
                    "matched": matched,
                    "message": self._make_message(reason, matched, lang),
                }

        # 2) 영어/단어 경계 매칭 (리트스피크 정규화 후)
        if self._wb_pattern:
            normalized = _normalize_for_en(text)
            m = self._wb_pattern.search(normalized)
            if m:
                matched = m.group(0)
                reason = self._categorize(matched)
                return {
                    "blocked": True,
                    "reason": reason,
                    "matched": matched,
                    "message": self._make_message(reason, matched, lang),
                }

        return {"blocked": False}

    def check_many(self, texts: list[str], lang: str = "ko") -> dict:
        """여러 입력 칸을 한 번에 검사. 처음 걸린 항목의 결과를 반환."""
        for t in texts:
            result = self.check(t or "", lang=lang)
            if result["blocked"]:
                return result
        return {"blocked": False}

    @staticmethod
    def _make_message(reason: str, matched: str, lang: str = "ko") -> str:
        if lang == "en":
            if reason == "danger_speed":
                return (
                    "Words like that can be dangerous for the Hamster robot.\n"
                    "Could you try again with a safer speed?"
                )
            if reason == "danger_action":
                return (
                    "That action could damage the Hamster robot or nearby objects.\n"
                    "Could you try a safe command instead?"
                )
            return (
                "Your input contains words we shouldn't use.\n"
                "Could you write it politely, the way you would to a teacher or friend?"
            )

        if reason == "danger_speed":
            return (
                f"'{matched}' 같은 말은 햄스터봇에게 위험할 수 있어요.\n"
                "좀 더 안전한 속도로 다시 입력해 볼까요?"
            )
        if reason == "danger_action":
            return (
                f"'{matched}' 동작은 햄스터봇이나 주변 물건을 다치게 할 수 있어요.\n"
                "안전한 명령으로 다시 시도해 볼까요?"
            )
        return (
            "좋지 않은 말이 포함되어 있어요.\n"
            "선생님이나 친구에게 쓰는 것처럼 예의 바르게 입력해 줄 수 있나요?"
        )


# 싱글턴 인스턴스 (앱 전체에서 재사용)
safety_filter = SafetyFilter(_SUBSTRING_TERMS, _WORDBOUNDARY_TERMS)
