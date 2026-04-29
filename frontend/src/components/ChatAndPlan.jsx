// frontend/src/components/ChatAndPlan.jsx
//
// PIE BRIDGE - 목표 입력 + 행동 계획 표시 + 5가지 선택 컴포넌트

import { useState, useRef, useCallback } from "react";
import { generatePlan, generateCode } from "../services/api";

const CODE_BTN_COOLTIME_MS = 3000;
const MAX_GOAL_LENGTH = 100;

// ── 선택지 정의 (이모지 제거) ──────────────────────────
const CHOICES = [
  {
    id: 1,
    label: "이대로 실행하기",
    desc: "계획한 대로 그대로 실행해요",
    color: "bg-gradient-to-br from-orange-400 to-rose-500 border-orange-500",
    textColor: "text-white",
  },
  {
    id: 4,
    label: "장애물 회피 우선하기",
    desc: "사진 속 장애물과 부딪힐 것 같으면 목표 도착보다 회피를 더 우선해요",
    color: "bg-gradient-to-br from-amber-400 to-orange-500 border-amber-500",
    textColor: "text-white",
  },
  {
    id: 5,
    label: "더 효율적으로 계획하기",
    desc: "최단 경로로 빠르게 이동해요",
    color: "bg-gradient-to-br from-fuchsia-500 to-purple-500 border-fuchsia-500",
    textColor: "text-white",
  },
  {
    id: 3,
    label: "다시 계획 세우기",
    desc: "같은 사진과 같은 목표로 계획만 새로 만들어요",
    color: "bg-white hover:bg-orange-50 border-orange-200",
    textColor: "text-orange-600",
  },
];

// ── 목표 입력 폼 ─────────────────────────────────────────────
function GoalInput({ value, onChange, onSubmit, isLoading, obstacles, boardDetected, hamsterPosition }) {
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="space-y-2">
      {/* 분석 정보 요약 (편집 결과 그대로 표시) */}
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className={`
            px-2.5 py-1 rounded-full text-xs font-extrabold border-2
            ${boardDetected
              ? "bg-sky-50 text-sky-700 border-sky-300"
              : "bg-gray-50 text-gray-600 border-gray-300"}
          `}>
            {boardDetected ? "발판(말판) 있음 - 보드 명령어 사용" : "발판 없음 - 시간 제어 방식"}
          </span>
          {hamsterPosition && (
            <span className="px-2.5 py-1 rounded-full text-xs font-bold border-2
                             bg-sky-50 text-sky-700 border-sky-200">
              햄스터봇 위치: {hamsterPosition}
            </span>
          )}
        </div>
        {obstacles.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {obstacles.map((obs, i) => {
              const name = typeof obs === "string" ? obs : (obs?.name ?? "");
              const pos = typeof obs === "string" ? "" : (obs?.position ?? "");
              return (
                <span key={i} className="px-2 py-0.5 bg-orange-100 text-orange-700
                                         rounded-full text-xs font-bold border-2 border-orange-200">
                  {name}{pos ? ` - ${pos}` : ""}
                </span>
              );
            })}
          </div>
        )}
      </div>

      <div className="relative">
        <textarea
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value.slice(0, MAX_GOAL_LENGTH))}
          onKeyDown={handleKeyDown}
          placeholder={"햄스터봇에게 어떻게 움직이면 좋을까요?\n(예: 책 옆을 돌아서 지우개 앞으로 가줘)\nShift+Enter로 줄바꿈, Enter로 제출"}
          className="goal-input-textarea notebook-input w-full px-3 py-2 pb-6 text-sm rounded-2xl border-2 border-sky-300
                     focus:border-sky-500 focus:outline-none focus:ring-4 focus:ring-sky-100
                     placeholder-sky-300 disabled:bg-gray-50 disabled:text-gray-400
                     resize-none shadow-inner"
          disabled={isLoading}
          maxLength={MAX_GOAL_LENGTH}
        />
        <span className="absolute right-3 bottom-2.5 text-xs text-sky-400 bg-white/80 px-1.5 rounded-full font-bold">
          {value.length}/{MAX_GOAL_LENGTH}
        </span>
      </div>

      <button
        onClick={onSubmit}
        disabled={isLoading || value.trim().length === 0}
        className="game-btn w-full px-4 py-2.5 bg-gradient-to-br from-sky-400 to-sky-600 hover:from-sky-500 hover:to-sky-700
                   disabled:from-gray-300 disabled:to-gray-400
                   text-white font-extrabold text-base rounded-2xl
                   shadow-[0_4px_0_0_rgb(2,132,199)] hover:shadow-[0_6px_0_0_rgb(2,132,199)]
                   disabled:shadow-[0_4px_0_0_rgb(156,163,175)]
                   disabled:cursor-not-allowed
                   flex items-center justify-center gap-2"
      >
        {isLoading ? (
          <>
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            계획 만드는 중...
          </>
        ) : "계획 세우기"}
      </button>
    </div>
  );
}

// ── 행동 계획 스텝 카드 ──────────────────────────────────────
function PlanStepCard({ step, action, detail, isAnimated, isLast }) {
  const STEP_COLORS = [
    "bg-emerald-50 border-emerald-300 text-emerald-700",
    "bg-lime-50 border-lime-300 text-lime-700",
    "bg-teal-50 border-teal-300 text-teal-700",
  ];
  const BADGE_COLORS = [
    "bg-emerald-500 text-white",
    "bg-lime-500 text-white",
    "bg-teal-500 text-white",
  ];
  const colorClass = STEP_COLORS[(step - 1) % STEP_COLORS.length];
  const badgeClass = BADGE_COLORS[(step - 1) % BADGE_COLORS.length];

  return (
    <div className="relative">
      <div
        className={`
          kid-card flex gap-2 p-2.5 rounded-2xl border-2 ${colorClass}
          ${isAnimated ? "animate-fade-in" : ""}
          shadow-md
        `}
      >
        <div className={`flex-shrink-0 w-7 h-7 rounded-full ${badgeClass}
                         flex items-center justify-center font-black text-sm
                         shadow-md ring-2 ring-white`}>
          {step}
        </div>
        <div className="space-y-0.5 min-w-0">
          <p className="font-extrabold text-sm leading-snug">{action}</p>
          <p className="text-xs opacity-80 leading-snug font-semibold">{detail}</p>
        </div>
      </div>
      {!isLast && (
        <div className="flex justify-center -my-1 relative z-10 pointer-events-none">
          <span className="text-emerald-500 text-lg leading-none drop-shadow-sm">⬇</span>
        </div>
      )}
    </div>
  );
}

// ── 5가지 선택 버튼 그룹 ─────────────────────────────────────
function ChoiceButtons({ onChoose, selectedId, isCooltime }) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-extrabold text-gray-700">
        어떻게 실행할까요? 하나를 골라요.
      </p>

      <div className="grid grid-cols-1 gap-2">
        {CHOICES.map((choice) => {
          const isSelected = selectedId === choice.id;
          const isDisabled = isCooltime && !isSelected;

          return (
            <button
              key={choice.id}
              onClick={() => onChoose(choice.id)}
              disabled={isDisabled}
              className={`
                game-btn flex items-start gap-2 px-3 py-2 rounded-2xl border-2 text-left
                ${choice.color} ${choice.textColor}
                ${isSelected ? "ring-4 ring-orange-300 ring-offset-2 scale-[0.98] shadow-inner" : "shadow-lg"}
                ${isDisabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}
              `}
            >
              <div className="min-w-0">
                <p className="font-extrabold text-sm leading-snug">{choice.label}</p>
                <p className={`text-xs mt-0.5 leading-snug ${choice.textColor} opacity-85 font-semibold`}>
                  {choice.desc}
                </p>
              </div>
              {isSelected && (
                <span className={`ml-auto flex-shrink-0 font-extrabold text-[0.65rem]
                                 rounded-full px-2 py-0.5
                                 ${choice.id === 3 ? "bg-gray-800/10 text-gray-700" : "bg-white/30 text-white"}`}>
                  선택됨
                </span>
              )}
            </button>
          );
        })}
      </div>

      {isCooltime && (
        <p className="text-xs text-gray-400 text-center animate-pulse font-semibold">
          잠깐만요, 코드를 만들고 있어요. (3초 후 다시 선택할 수 있어요)
        </p>
      )}
    </div>
  );
}

function PlanSummaryBanner({ summary }) {
  return (
    <div className="px-4 py-2 bg-sky-50 border-2 border-sky-200
                    rounded-xl text-sm text-sky-800 font-semibold">
      <p className="leading-snug">{summary}</p>
    </div>
  );
}

function SafetyWarning({ message, onDismiss }) {
  return (
    <div className="flex items-start gap-4 p-6 bg-amber-50 border-2 border-amber-300 rounded-2xl">
      <div className="flex-1 min-w-0">
        <p className="font-extrabold text-amber-800 text-xl">잠깐만요</p>
        <p className="text-amber-700 text-base mt-2 whitespace-pre-wrap font-semibold">{message}</p>
      </div>
      <button
        onClick={onDismiss}
        className="flex-shrink-0 text-amber-500 hover:text-amber-700 text-2xl leading-none font-bold"
        title="닫기"
      >
        X
      </button>
    </div>
  );
}

function ErrorBanner({ message, onRetry }) {
  return (
    <div className="flex items-center gap-4 p-5 bg-red-50 border-2 border-red-200 rounded-2xl">
      <p className="text-red-700 text-base flex-1 font-semibold">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex-shrink-0 px-5 py-2.5 bg-red-100 hover:bg-red-200
                     text-red-700 text-sm font-extrabold rounded-full transition-colors"
        >
          다시 시도
        </button>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// 메인 컴포넌트: ChatAndPlan
// ─────────────────────────────────────────────────────────────

export default function ChatAndPlan({
  base64Image,
  obstacles = [],
  hamsterPosition = "",
  userId = "anonymous",
  platform = "entry",
  boardDetected = false,
  hamsterFacing = "unknown",
  goal: goalProp,
  onGoalChange,
  onCodeReady,
  onPlanReady,
  onSafetyBlock,
  onPlanGenerated,
  onChoiceMade,
}) {
  const [goalLocal, setGoalLocal] = useState("");
  const goal = goalProp !== undefined ? goalProp : goalLocal;
  const setGoal = onGoalChange ?? setGoalLocal;
  const [plan, setPlan]               = useState(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [codeLoading, setCodeLoading] = useState(false);
  const [selectedChoice, setSelectedChoice] = useState(null);
  const [isCooltime, setIsCooltime]   = useState(false);
  const [safetyMsg, setSafetyMsg]     = useState("");
  const [error, setError]             = useState("");
  // 같은 목표로 다시 계획을 만든 경우 안내 배너용
  const [replanNotice, setReplanNotice] = useState("");

  const cooltimeRef = useRef(null);

  // 계획 생성 (최초 + 다시 계획 모두 사용)
  const runGeneratePlan = useCallback(async (isReplan) => {
    if (!goal.trim() || planLoading) return;

    setSafetyMsg("");
    setError("");
    setReplanNotice("");
    if (!isReplan) {
      setPlan(null);
    }
    setSelectedChoice(null);
    setPlanLoading(true);

    try {
      const result = await generatePlan(
        base64Image, goal, obstacles, userId,
        boardDetected, hamsterFacing, hamsterPosition,
      );

      if (result.blocked) {
        const msg = result.message ?? "위험한 내용이 감지되었어요.";
        setSafetyMsg(msg);
        onSafetyBlock?.(goal.trim());
        return;
      }

      if (result.error || !Array.isArray(result.steps) || result.steps.length === 0) {
        setError(result.error ?? "AI가 계획을 만들지 못했어요. 목표를 다시 입력해 볼까요?");
        return;
      }

      setPlan(result);
      onPlanGenerated?.();
      onPlanReady?.(result);
      if (isReplan) {
        setReplanNotice("같은 목표로 새 계획을 다시 만들었어요. 아래에서 다시 골라 보세요.");
      }
    } catch (e) {
      setError(e.message ?? "계획을 만들지 못했어요. 다시 시도해 볼까요?");
    } finally {
      setPlanLoading(false);
    }
  }, [goal, planLoading, base64Image, obstacles, userId, boardDetected, hamsterFacing, hamsterPosition, onSafetyBlock, onPlanGenerated, onPlanReady]);

  const handleGeneratePlan = useCallback(() => runGeneratePlan(false), [runGeneratePlan]);

  const handleChoose = useCallback(async (choiceId) => {
    if (isCooltime || codeLoading) return;

    onChoiceMade?.(choiceId);

    // 선택지 3: 같은 사진/목표로 계획만 다시 세우기 (코드 생성 X)
    if (choiceId === 3) {
      setSelectedChoice(3);
      runGeneratePlan(true);
      // 짧은 쿨타임으로 중복 클릭만 막음
      setIsCooltime(true);
      cooltimeRef.current = setTimeout(() => setIsCooltime(false), 1500);
      return;
    }

    setSelectedChoice(choiceId);
    setIsCooltime(true);
    setCodeLoading(true);
    setError("");

    cooltimeRef.current = setTimeout(() => {
      setIsCooltime(false);
    }, CODE_BTN_COOLTIME_MS);

    try {
      const result = await generateCode(
        plan, choiceId, userId, platform, boardDetected,
        goal, hamsterPosition, obstacles,
      );
      onCodeReady?.({ ...result, _selectedChoice: choiceId });
    } catch (e) {
      setError(e.message ?? "코드를 만들지 못했어요. 다시 선택해 볼까요?");
      setSelectedChoice(null);
    } finally {
      setCodeLoading(false);
    }
  }, [isCooltime, codeLoading, plan, userId, platform, boardDetected, goal, hamsterPosition, obstacles, onCodeReady, onChoiceMade, runGeneratePlan]);

  return (
    <section className="w-full max-w-7xl mx-auto space-y-3">

      <div className="flex items-center gap-2">
        <span className="inline-flex items-center justify-center w-8 h-8 rounded-full
                         bg-sky-500 text-white font-black text-base shadow-md">2</span>
        <h2 className="text-xl font-black text-gray-800 tracking-tight">
          햄스터봇에게 뭘 시킬까요?
        </h2>
      </div>

      {!plan && (
        <div className="kid-card bg-white rounded-3xl shadow-xl border-4 border-sky-200 overflow-hidden">
          <div className="px-4 py-2 bg-gradient-to-r from-sky-300 to-sky-500 flex items-center gap-2">
            <img src="/mascots/goal-icon.png" alt="목표"
                 className="w-9 h-9 object-contain drop-shadow animate-floaty" />
            <p className="text-sm font-extrabold text-white tracking-wide">목표 입력</p>
          </div>
          <div className="p-4 space-y-3">
            <p className="speech-bubble text-sm text-sky-800 font-semibold">
              사진 속 햄스터봇이 어떻게 움직였으면 좋겠는지 써 주세요.
            </p>
            <GoalInput
              value={goal}
              onChange={setGoal}
              onSubmit={handleGeneratePlan}
              isLoading={planLoading}
              obstacles={obstacles}
              boardDetected={boardDetected}
              hamsterPosition={hamsterPosition}
            />
          </div>
        </div>
      )}

      {safetyMsg && (
        <SafetyWarning
          message={safetyMsg}
          onDismiss={() => setSafetyMsg("")}
        />
      )}

      {error && (
        <ErrorBanner
          message={error}
          onRetry={plan ? undefined : handleGeneratePlan}
        />
      )}

      {planLoading && (
        <div className="space-y-4 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 bg-gray-100 rounded-2xl" />
          ))}
        </div>
      )}

      {plan && !planLoading && (
        <div className="space-y-3">

          {replanNotice && (
            <div className="px-4 py-2 bg-emerald-50 border-2 border-emerald-200
                            rounded-xl text-sm text-emerald-800 font-semibold">
              {replanNotice}
            </div>
          )}

          {plan.summary && <PlanSummaryBanner summary={plan.summary} />}

          <div className="grid grid-cols-1 lg:grid-cols-[3fr_4fr_3fr] gap-3 items-start">

            <div className="kid-card bg-white rounded-3xl shadow-xl border-4 border-sky-200 overflow-hidden">
              <div className="px-4 py-2 bg-gradient-to-r from-sky-300 to-sky-500 flex items-center gap-2">
                <img src="/mascots/goal-icon.png" alt="목표"
                     className="w-9 h-9 object-contain drop-shadow animate-floaty" />
                <p className="text-sm font-extrabold text-white tracking-wide">목표 입력</p>
              </div>
              <div className="p-3 space-y-2">
                <p className="speech-bubble text-xs text-sky-800 font-semibold">
                  사진 속 햄스터봇이 어떻게 움직였으면 좋겠는지 써 주세요.
                </p>
                <GoalInput
                  value={goal}
                  onChange={setGoal}
                  onSubmit={handleGeneratePlan}
                  isLoading={planLoading}
                  obstacles={obstacles}
                  boardDetected={boardDetected}
                  hamsterPosition={hamsterPosition}
                />
              </div>
            </div>

            <div className="kid-card bg-white rounded-3xl shadow-xl border-4 border-emerald-200 overflow-hidden relative">
              <div className="px-4 py-2 bg-gradient-to-r from-emerald-300 to-emerald-500 flex items-center gap-2">
                <img src="/mascots/ai-hamster.png" alt="AI 햄스터"
                     className="w-9 h-9 object-contain drop-shadow animate-floaty" />
                <p className="text-sm font-extrabold text-white tracking-wide">
                  AI 선생님이 세운 계획
                  {Array.isArray(plan.steps) && plan.steps.length > 0 && ` (총 ${plan.steps.length}단계)`}
                </p>
              </div>
              <div className="p-3 space-y-2 bg-gradient-to-b from-emerald-50/40 to-white">
              {Array.isArray(plan.steps) && plan.steps.length > 0 ? (
                plan.steps.map((step, i, arr) => (
                  <PlanStepCard
                    key={step.step}
                    step={step.step}
                    action={step.action}
                    detail={step.detail}
                    isAnimated={true}
                    isLast={i === arr.length - 1}
                  />
                ))
              ) : (
                <div className="py-2 px-3 bg-amber-50 border-2 border-amber-200 rounded-xl text-sm text-amber-700 font-semibold">
                  계획을 가져오지 못했어요. 목표를 다시 입력해 볼까요?
                </div>
              )}
              </div>
            </div>

            <div>
              {codeLoading ? (
                <div className="flex flex-col items-center justify-center gap-2 py-5
                                bg-orange-50 rounded-3xl border-4 border-orange-200 h-full shadow-xl">
                  <img src="/mascots/hamster-cheer.png" alt=""
                       className="w-12 h-12 object-contain animate-floaty" />
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 border-4 border-orange-300 border-t-orange-500
                                    rounded-full animate-spin" />
                    <p className="text-orange-700 font-extrabold text-sm animate-pulse">
                      선생님이 파이썬 코드를 만들고 있어요...
                    </p>
                  </div>
                </div>
              ) : (
                <div className="kid-card bg-white rounded-3xl shadow-xl border-4 border-orange-200 overflow-hidden">
                  <div className="px-4 py-2 bg-gradient-to-r from-orange-300 to-orange-500 flex items-center gap-2">
                    <img src="/mascots/trophy-kid.png" alt="실행"
                         className="w-9 h-9 object-contain drop-shadow animate-floaty" />
                    <p className="text-sm font-extrabold text-white tracking-wide">
                      실행 방법 고르기
                    </p>
                  </div>
                  <div className="p-3 bg-gradient-to-b from-orange-50/40 to-white">
                    <ChoiceButtons
                      onChoose={handleChoose}
                      selectedId={selectedChoice}
                      isCooltime={isCooltime}
                    />
                  </div>
                </div>
              )}
            </div>

          </div>
        </div>
      )}
    </section>
  );
}
