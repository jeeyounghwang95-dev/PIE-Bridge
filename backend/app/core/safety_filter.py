# backend/app/core/safety_filter.py
#
# PIE BRIDGE - 안전 필터 (Safety Guardrails)
#
# 위험 키워드 / 욕설 감지 시:
#   - 파이썬 코드 생성 차단
#   - safety_logs DB에 기록 (ai_routes.py 에서 호출)
#   - 친절한 경고 메시지 반환
#
# 욕설 목록: profanity_ko.txt (HuggingFace 2tle/korean-curse-filtering-dataset 기반)
#   목록 갱신 시 profanity_ko.txt 만 수정하면 됨 (서버 재시작 필요)

import re
from pathlib import Path


# ── 위험 행동 키워드 목록 ──────────────────────────────────────

_DANGER_SPEED = [
    "전속력", "최고속도", "최대 속도", "풀 속도", "100% 속도",
    "제일 빠르게", "가장 빠르게",
]

_DANGER_ACTION = [
    "떨어뜨려", "떨어져", "충돌", "부숴", "파괴", "망가뜨려",
    "밀어", "때려", "공격",
]


# ── 욕설 목록: profanity_ko.txt 에서 로드 ─────────────────────

def _load_profanity(path: Path) -> list[str]:
    """txt 파일에서 욕설 단어를 읽어 반환. # 주석·빈 줄 무시."""
    if not path.exists():
        return []
    words = []
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.split("#")[0].strip()
        if word:
            words.append(word)
    return words


_PROFANITY = _load_profanity(Path(__file__).parent / "profanity_ko.txt")

# 모든 키워드를 하나의 리스트로 합침
_ALL_BLOCKED = _DANGER_SPEED + _DANGER_ACTION + _PROFANITY


class SafetyFilter:
    """
    입력 텍스트에서 위험 키워드를 감지한다.

    사용법:
        result = safety_filter.check("전속력으로 앞으로 가줘")
        # result → {"blocked": True, "reason": "danger_speed", "message": "..."}
    """

    def __init__(self, blocked_words: list[str]) -> None:
        # 대소문자 무시, 단어 경계 없이 매칭 (한국어 지원)
        patterns = [re.escape(w) for w in blocked_words]
        self._pattern = re.compile("|".join(patterns), re.IGNORECASE) if patterns else None

    @staticmethod
    def _categorize(word: str) -> str:
        if word in _DANGER_SPEED:
            return "danger_speed"
        if word in _DANGER_ACTION:
            return "danger_action"
        return "profanity"

    def check(self, text: str) -> dict:
        """
        Returns:
            {"blocked": False}
            또는
            {"blocked": True, "reason": str, "matched": str, "message": str}
        """
        if not self._pattern:
            return {"blocked": False}

        match = self._pattern.search(text)
        if not match:
            return {"blocked": False}

        matched_word = match.group(0)
        reason = self._categorize(matched_word.lower())
        message = self._make_message(reason, matched_word)

        return {
            "blocked": True,
            "reason": reason,
            "matched": matched_word,
            "message": message,
        }

    @staticmethod
    def _make_message(reason: str, matched: str) -> str:
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
safety_filter = SafetyFilter(_ALL_BLOCKED)
