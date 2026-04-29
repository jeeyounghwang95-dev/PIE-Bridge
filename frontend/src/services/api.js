// frontend/src/services/api.js
//
// PIE BRIDGE - FastAPI 백엔드 통신 서비스
//
// 모든 fetch 호출을 여기에 집중시켜서
// URL 변경, 헤더 추가 등을 한 곳에서 관리합니다.

// vite.config.js 에서 /api → localhost:8000 프록시 설정되어 있음
const BASE_URL = import.meta.env.VITE_API_URL ?? "";

// ── 공통 POST 헬퍼 ─────────────────────────────────────────
async function post(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "알 수 없는 오류" }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }

  return res.json();
}

// ── 1-A단계: 이미지 품질 검사 ──────────────────────────────
/**
 * @param {string} base64Image  - 프론트에서 리사이징된 base64 문자열
 * @param {string} userId
 * @returns {Promise<{passed: boolean, reason: string, obstacles_detected: string[]}>}
 */
export function analyzeImage(base64Image, userId = "anonymous") {
  return post("/api/ai/analyze-image", {
    base64_image: base64Image,
    user_id: userId,
  });
}

// ── 1-B단계: 행동 계획 생성 ────────────────────────────────
/**
 * @param {string}   base64Image
 * @param {string}   studentGoal      - 학생이 입력한 목표
 * @param {Array<{name:string, position:string}>} obstacles
 * @param {string}   userId
 * @param {boolean}  boardDetected
 * @param {string}   hamsterFacing
 * @param {string}   hamsterPosition  - 햄스터봇 위치 (1단계 분석 결과)
 * @returns {Promise<{steps: object[], summary: string}>}
 */
export function generatePlan(
  base64Image,
  studentGoal,
  obstacles = [],
  userId = "anonymous",
  boardDetected = false,
  hamsterFacing = "unknown",
  hamsterPosition = "",
) {
  return post("/api/ai/generate-plan", {
    base64_image: base64Image,
    student_goal: studentGoal,
    obstacles,
    user_id: userId,
    board_detected: boardDetected,
    hamster_facing: hamsterFacing,
    hamster_position: hamsterPosition,
  });
}

// ── 3단계: 파이썬 코드 생성 ────────────────────────────────
/**
 * @param {object} actionPlan
 * @param {number} studentChoice
 * @param {string} userId
 * @param {string} platform
 * @param {boolean} boardDetected
 * @param {string} studentGoal
 * @param {string} hamsterPosition
 * @param {Array<{name:string, position:string}>} obstacles
 */
export function generateCode(
  actionPlan,
  studentChoice,
  userId = "anonymous",
  platform = "entry",
  boardDetected = false,
  studentGoal = "",
  hamsterPosition = "",
  obstacles = [],
) {
  return post("/api/ai/generate-code", {
    action_plan: actionPlan,
    student_choice: studentChoice,
    user_id: userId,
    platform,
    board_detected: boardDetected,
    student_goal: studentGoal,
    hamster_position: hamsterPosition,
    obstacles,
  });
}
