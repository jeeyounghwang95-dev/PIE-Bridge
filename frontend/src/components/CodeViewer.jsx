// frontend/src/components/CodeViewer.jsx
//
// PIE BRIDGE - 코드 뷰어 컴포넌트
//
// 역할:
//   1. AI 선생님의 Vibe-Explanation 표시
//   2. 파이썬 코드를 문법 하이라이팅과 함께 표시
//   3. [📋 파이썬 코드 복사하기] 버튼으로 클립보드 복사
//
// 의존성:
//   npm install react-syntax-highlighter
//   (TailwindCSS는 전역 설정 가정)

import { useState, useCallback } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

// ── 상수 ─────────────────────────────────────────────────────
const COPY_RESET_DELAY_MS = 2500;

const CHOICE_INFO = {
  1: { label: "이대로 실행하기",    desc: "원래 계획 그대로 구현",        bg: "bg-indigo-50", text: "text-indigo-800", border: "border-indigo-300" },
  2: { label: "더 안전하게",        desc: "속도를 낮춰서 천천히",          bg: "bg-green-50",  text: "text-green-800",  border: "border-green-300"  },
  4: { label: "장애물 회피 우선",   desc: "사진 기준 충돌 위험 시 회피 우선", bg: "bg-amber-50",  text: "text-amber-800",  border: "border-amber-300"  },
  5: { label: "더 효율적으로",      desc: "최단 경로로 최적화",            bg: "bg-purple-50", text: "text-purple-800", border: "border-purple-300" },
};

function CodeConditionBadges({ choiceId, boardDetected }) {
  const info = CHOICE_INFO[choiceId];
  return (
    <div className="flex flex-wrap gap-1.5">
      {info && (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-extrabold border-2 ${info.bg} ${info.text} ${info.border}`}>
          {info.label}
        </span>
      )}
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-extrabold border-2
        ${boardDetected ? "bg-sky-50 text-sky-700 border-sky-300" : "bg-gray-100 text-gray-600 border-gray-300"}`}>
        {boardDetected ? "발판 보드 방식" : "시간 제어 방식"}
      </span>
    </div>
  );
}

// ── 로딩 스피너 (Tailwind 애니메이션) ──────────────────────
function LoadingSpinner() {
  return (
    <div className="flex flex-col items-center justify-center gap-6 py-20">
      <div className="w-20 h-20 border-4 border-sky-300 border-t-sky-500 rounded-full animate-spin" />
      <p className="text-sky-600 font-extrabold text-2xl animate-pulse">
        선생님이 코드를 만들고 있어요...
      </p>
    </div>
  );
}

function ErrorBanner({ message }) {
  return (
    <div className="p-4 bg-red-50 border border-red-200 rounded-xl">
      <p className="font-bold text-red-700">문제가 생겼어요</p>
      <p className="text-red-600 text-sm mt-1">{message}</p>
    </div>
  );
}

function SafetyBlockBanner({ message }) {
  return (
    <div className="p-4 bg-amber-50 border-2 border-amber-300 rounded-xl">
      <p className="font-bold text-amber-800 text-lg">잠깐만요</p>
      <p className="text-amber-700 mt-1">{message}</p>
      <p className="text-amber-600 text-sm mt-2">
        다른 방법으로 다시 시도해 볼까요?
      </p>
    </div>
  );
}

function TeacherExplanation({ text }) {
  const paragraphs = String(text ?? "")
    .split(/\n+/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0);

  return (
    <div className="mb-2">
      <p className="text-xs font-extrabold text-sky-600 mb-1 tracking-wide">AI 선생님 설명</p>
      <div className="bg-sky-50 border-2 border-sky-200 rounded-xl px-3 py-2 shadow-sm">
        {paragraphs.length > 0 ? (
          paragraphs.map((p, i) => (
            <p
              key={i}
              className={`text-sky-900 leading-snug text-xs font-semibold indent-3 ${i < paragraphs.length - 1 ? "mb-2" : ""}`}
            >
              {p}
            </p>
          ))
        ) : (
          <p className="text-sky-900 leading-snug text-xs font-semibold indent-3">{text}</p>
        )}
      </div>
    </div>
  );
}

// ── 복사 버튼 ────────────────────────────────────────────────
function CopyButton({ code }) {
  const [copied, setCopied] = useState(false);
  const [isDebouncing, setIsDebouncing] = useState(false); // 3초 쿨타임

  const handleCopy = useCallback(async () => {
    // 쿨타임 중이면 무시
    if (isDebouncing || copied) return;

    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setIsDebouncing(true);

      // 2.5초 후 버튼 원상복귀
      setTimeout(() => {
        setCopied(false);
        setIsDebouncing(false);
      }, COPY_RESET_DELAY_MS);
    } catch {
      // 클립보드 API 미지원 환경 (구형 브라우저) 대응
      // execCommand 폴백
      const textarea = document.createElement("textarea");
      textarea.value = code;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), COPY_RESET_DELAY_MS);
    }
  }, [code, copied, isDebouncing]);

  return (
    <button
      onClick={handleCopy}
      disabled={isDebouncing}
      className={`
        flex items-center gap-1.5 px-3 py-1 rounded-full font-extrabold text-xs whitespace-nowrap
        transition-all duration-200 shadow-md active:scale-95
        ${copied
          ? "bg-green-500 text-white cursor-default"
          : isDebouncing
          ? "bg-gray-300 text-gray-500 cursor-not-allowed"
          : "bg-sky-500 hover:bg-sky-600 text-white cursor-pointer hover:shadow-lg"
        }
      `}
      title={copied ? "복사 완료" : "파이썬 코드를 클립보드에 복사합니다"}
    >
      <span>{copied ? "복사 완료" : "파이썬 코드 복사하기"}</span>
    </button>
  );
}

// ── 코드 블록 (하이라이팅 + 복사 버튼) ─────────────────────
function CodeBlock({ code }) {
  return (
    <div className="relative rounded-lg overflow-hidden shadow-lg border border-gray-700">
      {/* 상단 바: 파일명 + 복사 버튼 */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-gray-800">
        <div className="flex items-center gap-1.5">
          {/* macOS 스타일 신호등 점 */}
          <span className="w-2.5 h-2.5 rounded-full bg-red-400 inline-block" />
          <span className="w-2.5 h-2.5 rounded-full bg-yellow-400 inline-block" />
          <span className="w-2.5 h-2.5 rounded-full bg-green-400 inline-block" />
          <span className="ml-1.5 text-gray-400 text-xs font-mono">
            hamster_code.py
          </span>
        </div>
        {/* 복사 버튼: 우측 상단 배치 */}
        <CopyButton code={code} />
      </div>

      {/* 코드 하이라이팅 */}
      <SyntaxHighlighter
        language="python"
        style={vscDarkPlus}
        showLineNumbers={true}
        lineNumberStyle={{ color: "#555", minWidth: "2em" }}
        customStyle={{
          margin: 0,
          borderRadius: 0,
          fontSize: "0.75rem",
          lineHeight: "1.45",
          maxHeight: "320px",
          overflowY: "auto",
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

// ── 계획 비교 섹션 ───────────────────────────────────────────
const STEP_COLORS = [
  { bg: "bg-sky-50", border: "border-sky-200", text: "text-sky-700", badge: "bg-sky-100" },
  { bg: "bg-violet-50", border: "border-violet-200", text: "text-violet-700", badge: "bg-violet-100" },
  { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700", badge: "bg-emerald-100" },
  { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", badge: "bg-amber-100" },
];

function PlanStep({ step, action, detail, faded = false }) {
  const c = STEP_COLORS[(step - 1) % STEP_COLORS.length];
  return (
    <div className={`flex gap-3 p-3 rounded-xl border-2 ${c.bg} ${c.border} ${faded ? "opacity-50" : ""}`}>
      <div className={`flex-shrink-0 w-7 h-7 rounded-full ${c.badge} flex items-center justify-center font-bold text-xs ${c.text}`}>
        {step}
      </div>
      <div className="space-y-0.5 min-w-0">
        <p className={`font-bold text-xs leading-snug ${c.text}`}>{action}</p>
        <p className={`text-xs opacity-70 leading-relaxed ${c.text}`}>{detail}</p>
      </div>
    </div>
  );
}

function PlanComparisonSection({ planChanged, changeReason, originalPlan, modifiedSteps }) {
  const originalSteps = originalPlan?.steps ?? [];

  if (!planChanged) {
    return (
      <div className="rounded-lg border-2 border-gray-200 bg-gray-50 p-2 space-y-1">
        <p className="font-bold text-gray-600 text-xs">이동 계획 변경 여부</p>
        <div className="px-2.5 py-1.5 bg-white rounded-md border border-gray-200">
          <p className="font-bold text-gray-700 text-xs">변한 계획이 없어요</p>
          {changeReason && (
            <p className="text-gray-500 text-xs mt-0.5">{changeReason}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border-2 border-orange-200 bg-orange-50 p-2.5 space-y-2">
      <p className="font-bold text-orange-700 text-xs">이동 계획이 바뀌었어요</p>
      {changeReason && (
        <p className="text-orange-600 text-xs px-1">{changeReason}</p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-2">
          <p className="text-xs font-bold text-gray-500">원래 계획</p>
          <div className="space-y-1.5">
            {originalSteps.map((s) => (
              <PlanStep key={s.step} step={s.step} action={s.action} detail={s.detail} faded={true} />
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <p className="text-xs font-bold text-orange-600">바뀐 계획</p>
          <div className="space-y-1.5">
            {modifiedSteps.map((s) => (
              <PlanStep key={s.step} step={s.step} action={s.action} detail={s.detail} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function PasteGuide() {
  const steps = [
    "위 버튼을 눌러 코드를 복사해요",
    "블록컴포저 사이트를 열어요",
    "코드 창에 Ctrl+V 로 붙여넣기 해요",
    "실행 버튼을 눌러 햄스터봇을 움직여요",
  ];

  return (
    <div className="p-2 bg-green-50 border-2 border-green-200 rounded-lg h-full">
      <p className="font-extrabold text-green-800 text-xs mb-1">다음 단계: IDE에서 실행하기</p>
      <ol className="space-y-0.5">
        {steps.map((text, i) => (
          <li key={i} className="text-xs text-green-700 font-semibold">
            <strong>{i + 1}단계.</strong> {text}
          </li>
        ))}
      </ol>
    </div>
  );
}

// ── AI 선생님의 계획 평가 (SMILE FACE 3단계) ────────────────
const SMILE_LEVELS = [
  {
    id: "good",
    emoji: "😀",
    label: "좋아요",
    desc: "계획이 잘 짜여졌어요",
    bg: "bg-green-50",
    border: "border-green-300",
    text: "text-green-700",
    activeBg: "bg-green-500",
    activeBorder: "border-green-600",
  },
  {
    id: "soso",
    emoji: "😐",
    label: "보통",
    desc: "그저 그래요",
    bg: "bg-yellow-50",
    border: "border-yellow-300",
    text: "text-yellow-700",
    activeBg: "bg-yellow-400",
    activeBorder: "border-yellow-500",
  },
  {
    id: "hard",
    emoji: "😟",
    label: "아쉬워요",
    desc: "계획이 부족해요",
    bg: "bg-red-50",
    border: "border-red-300",
    text: "text-red-700",
    activeBg: "bg-red-500",
    activeBorder: "border-red-600",
  },
];

function PlanEvaluation({ codeKey, onEvaluate }) {
  const [selected, setSelected] = useState(null);

  // 새 코드가 들어오면 평가 상태 초기화 (codeKey 변경 감지)
  const [lastKey, setLastKey] = useState(codeKey);
  if (lastKey !== codeKey) {
    setLastKey(codeKey);
    setSelected(null);
  }

  const handleClick = (level) => {
    if (selected) return; // 한 번 평가하면 잠금
    setSelected(level.id);
    onEvaluate?.(level.id);
  };

  return (
    <div className="p-2 bg-sky-50 border-2 border-sky-200 rounded-lg h-full flex flex-col">
      <p className="font-extrabold text-sky-800 text-xs mb-1">AI 선생님의 계획 평가하기</p>
      <p className="text-[0.65rem] text-sky-600 font-semibold mb-2">
        선생님의 계획이 어땠는지 알려주세요
      </p>
      <div className="grid grid-cols-3 gap-1.5 flex-1">
        {SMILE_LEVELS.map((lv) => {
          const isSelected = selected === lv.id;
          const isDimmed = selected && !isSelected;
          return (
            <button
              key={lv.id}
              onClick={() => handleClick(lv)}
              disabled={!!selected}
              className={`
                flex flex-col items-center justify-center gap-0.5 px-1 py-1.5 rounded-lg
                border-2 transition-all duration-200 active:scale-95
                ${isSelected
                  ? `${lv.activeBg} ${lv.activeBorder} text-white shadow-md`
                  : isDimmed
                  ? "bg-gray-50 border-gray-200 text-gray-400 opacity-50"
                  : `${lv.bg} ${lv.border} ${lv.text} hover:shadow-md cursor-pointer`}
              `}
              title={lv.desc}
            >
              <span className="text-2xl leading-none">{lv.emoji}</span>
              <span className="text-[0.7rem] font-extrabold leading-tight">{lv.label}</span>
            </button>
          );
        })}
      </div>
      {selected && (
        <p className="mt-1.5 text-[0.65rem] text-sky-700 font-bold text-center">
          평가가 기록되었어요!
        </p>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// 메인 컴포넌트: CodeViewer
// ─────────────────────────────────────────────────────────────

/**
 * CodeViewer Props:
 *
 * @param {boolean}  isLoading      - 코드 생성 중 로딩 상태
 * @param {string}   explanation    - AI 선생님의 Vibe-Explanation 텍스트
 * @param {string}   pythonCode     - 생성된 파이썬 코드 문자열
 * @param {string}   error          - 에러 메시지 (없으면 null)
 * @param {boolean}  safetyBlocked  - 안전 필터 차단 여부
 * @param {string}   safetyMessage  - 안전 필터 차단 메시지
 * @param {boolean}  replan         - 재계획 요청 여부 (선택지 3번)
 */
export default function CodeViewer({
  isLoading = false,
  explanation = "",
  pythonCode = "",
  error = null,
  safetyBlocked = false,
  safetyMessage = "",
  replan = false,
  selectedChoice = null,
  boardDetected = false,
  originalPlan = null,
  planChanged = false,
  changeReason = "",
  modifiedSteps = [],
  onEvaluate = null,
}) {
  // ── 로딩 상태 ──────────────────────────────────────────────
  if (isLoading) {
    return (
      <section className="w-full max-w-3xl mx-auto p-6 bg-white rounded-2xl shadow-md">
        <LoadingSpinner />
      </section>
    );
  }

  // ── 안전 필터 차단 ─────────────────────────────────────────
  if (safetyBlocked) {
    return (
      <section className="w-full max-w-3xl mx-auto p-6 bg-white rounded-2xl shadow-md">
        <SafetyBlockBanner message={safetyMessage} />
      </section>
    );
  }

  // ── 에러 ──────────────────────────────────────────────────
  if (error) {
    return (
      <section className="w-full max-w-3xl mx-auto p-6 bg-white rounded-2xl shadow-md">
        <ErrorBanner message={error} />
      </section>
    );
  }

  if (replan) {
    return (
      <section className="w-full max-w-3xl mx-auto p-6 bg-white rounded-2xl shadow-md">
        <div className="text-center py-8">
          <p className="text-xl font-bold text-sky-600">새로운 계획을 세워볼까요?</p>
          <p className="text-gray-500 text-sm mt-1">
            왼쪽 단계에서 '다시 계획 세우기' 버튼을 눌러 주세요.
          </p>
        </div>
      </section>
    );
  }

  // ── 아직 코드가 없는 초기 상태 (컴포넌트만 마운트된 경우) ─
  if (!pythonCode && !explanation) {
    return null;
  }

  // ── 정상 렌더링: 설명 + 코드 + 붙여넣기 가이드 ────────────
  return (
    <section className="w-full bg-white rounded-xl shadow-md border-2 border-sky-100 overflow-hidden">
      <div className="px-3 py-1.5 bg-sky-500 flex items-center gap-1.5">
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full
                         bg-white text-sky-600 font-black text-xs shadow-sm">3</span>
        <h2 className="text-base font-black text-white tracking-tight">
          AI 선생님이 코드를 만들었어요
        </h2>
      </div>
      <div className="p-2.5 space-y-2">

      {/* 코드 생성 조건 배지 */}
      <CodeConditionBadges choiceId={selectedChoice} boardDetected={boardDetected} />

      {/* 계획 변경 비교 섹션 */}
      {(originalPlan || planChanged) && (
        <PlanComparisonSection
          planChanged={planChanged}
          changeReason={changeReason}
          originalPlan={originalPlan}
          modifiedSteps={modifiedSteps}
        />
      )}

      {/* AI 선생님 설명: 좌우로 폭이 넓도록 전체 너비로 표시 */}
      {explanation && (
        <div className="min-w-0">
          <TeacherExplanation text={explanation} />
        </div>
      )}

      {/* 코드 + 붙여넣기 가이드 + 평가 */}
      {pythonCode && (
        <div className="space-y-2 min-w-0">
          <CodeBlock code={pythonCode} />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 items-stretch">
            <PasteGuide />
            <PlanEvaluation codeKey={pythonCode} onEvaluate={onEvaluate} />
          </div>
        </div>
      )}

      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────
// 사용 예시 (부모 컴포넌트에서):
//
// const [codeData, setCodeData] = useState(null);
// const [loading, setLoading] = useState(false);
//
// const handleChoiceClick = async (choice) => {
//   setLoading(true);
//   const res = await fetch("/api/ai/generate-code", {
//     method: "POST",
//     headers: { "Content-Type": "application/json" },
//     body: JSON.stringify({ action_plan, student_choice: choice, user_id }),
//   });
//   const data = await res.json();
//   setCodeData(data);
//   setLoading(false);
// };
//
// <CodeViewer
//   isLoading={loading}
//   explanation={codeData?.explanation}
//   pythonCode={codeData?.python_code}
//   safetyBlocked={codeData?.blocked}
//   safetyMessage={codeData?.message}
//   replan={codeData?.replan}
// />
// ─────────────────────────────────────────────────────────────
