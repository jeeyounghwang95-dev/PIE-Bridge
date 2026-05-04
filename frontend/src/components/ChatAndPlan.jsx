// frontend/src/components/ChatAndPlan.jsx
//
// PIE BRIDGE - 목표 입력 + 행동 계획 표시 + 5가지 선택 컴포넌트

import { useState, useRef, useCallback, useMemo } from "react";
import { generatePlan, generateCode } from "../services/api";
import { useT } from "../i18n/LanguageContext";

const CODE_BTN_COOLTIME_MS = 3000;
const MAX_GOAL_LENGTH = 100;

// 선택지 색상은 언어와 무관하므로 상수로 유지하고, 텍스트만 t()로 채운다.
const CHOICE_STYLES = {
  1: {
    color: "bg-gradient-to-br from-orange-400 to-rose-500 border-orange-500",
    textColor: "text-white",
  },
  4: {
    color: "bg-gradient-to-br from-amber-400 to-orange-500 border-amber-500",
    textColor: "text-white",
  },
  5: {
    color: "bg-gradient-to-br from-fuchsia-500 to-purple-500 border-fuchsia-500",
    textColor: "text-white",
  },
  3: {
    color: "bg-white hover:bg-orange-50 border-orange-200",
    textColor: "text-orange-600",
  },
};

// ── 목표 입력 폼 ─────────────────────────────────────────────
function GoalInput({ value, onChange, onSubmit, isLoading, obstacles, boardDetected, hamsterPosition }) {
  const { t } = useT();
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
            {boardDetected ? t("plan.boardDetected") : t("plan.boardNotDetected")}
          </span>
          {hamsterPosition && (
            <span className="px-2.5 py-1 rounded-full text-xs font-bold border-2
                             bg-sky-50 text-sky-700 border-sky-200">
              {t("plan.hamsterPositionPrefix")}{hamsterPosition}
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
          placeholder={t("plan.goalCard.placeholder")}
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
            {t("plan.submitting")}
          </>
        ) : t("plan.submit")}
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
  const { t } = useT();
  const choices = useMemo(() => [
    { id: 1, label: t("plan.choice1.label"), desc: t("plan.choice1.desc"), ...CHOICE_STYLES[1] },
    { id: 4, label: t("plan.choice4.label"), desc: t("plan.choice4.desc"), ...CHOICE_STYLES[4] },
    { id: 5, label: t("plan.choice5.label"), desc: t("plan.choice5.desc"), ...CHOICE_STYLES[5] },
    { id: 3, label: t("plan.choice3.label"), desc: t("plan.choice3.desc"), ...CHOICE_STYLES[3] },
  ], [t]);

  return (
    <div className="space-y-2">
      <p className="text-sm font-extrabold text-gray-700">
        {t("plan.choices.title")}
      </p>

      <div className="grid grid-cols-1 gap-2">
        {choices.map((choice) => {
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
                                 rounded-full px-2 py-0.5 whitespace-nowrap
                                 ${choice.id === 3 ? "bg-gray-800/10 text-gray-700" : "bg-white/30 text-white"}`}>
                  {t("plan.choices.selected")}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {isCooltime && (
        <p className="text-xs text-gray-400 text-center animate-pulse font-semibold">
          {t("plan.choices.cooltime")}
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
  const { t } = useT();
  return (
    <div className="flex items-start gap-4 p-6 bg-amber-50 border-2 border-amber-300 rounded-2xl">
      <div className="flex-1 min-w-0">
        <p className="font-extrabold text-amber-800 text-xl">{t("plan.safety.headline")}</p>
        <p className="text-amber-700 text-base mt-2 whitespace-pre-wrap font-semibold">{message}</p>
      </div>
      <button
        onClick={onDismiss}
        className="flex-shrink-0 text-amber-500 hover:text-amber-700 text-2xl leading-none font-bold"
        title={t("plan.safety.close")}
      >
        X
      </button>
    </div>
  );
}

function ErrorBanner({ message, onRetry }) {
  const { t } = useT();
  return (
    <div className="flex items-center gap-4 p-5 bg-red-50 border-2 border-red-200 rounded-2xl">
      <p className="text-red-700 text-base flex-1 font-semibold">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex-shrink-0 px-5 py-2.5 bg-red-100 hover:bg-red-200
                     text-red-700 text-sm font-extrabold rounded-full transition-colors whitespace-nowrap"
        >
          {t("plan.error.retry")}
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
  onPromptLog,
  onPlanGenerated,
  onChoiceMade,
}) {
  const { t, lang } = useT();
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

    const submittedGoal = goal.trim();
    let loggedAsSafety = false;

    try {
      const result = await generatePlan(
        base64Image, goal, obstacles, userId,
        boardDetected, hamsterFacing, hamsterPosition, lang,
      );

      if (result.blocked) {
        const msg = result.message ?? t("plan.error.dangerous");
        setSafetyMsg(msg);
        // 새 입력일 때만 로그 (replan은 동일 프롬프트라 중복 방지)
        if (!isReplan) {
          onSafetyBlock?.(submittedGoal);
          loggedAsSafety = true;
        }
        return;
      }

      if (result.error || !Array.isArray(result.steps) || result.steps.length === 0) {
        setError(result.error ?? t("plan.error.cantMake"));
        return;
      }

      setPlan(result);
      onPlanGenerated?.();
      onPlanReady?.(result);
      if (isReplan) {
        setReplanNotice(t("plan.replanNotice"));
      }
    } catch (e) {
      setError(e.message ?? t("plan.error.cantMakeRetry"));
    } finally {
      setPlanLoading(false);
      // 새 입력일 때만 일반 프롬프트 로그 (이미 safety로 기록된 경우는 제외)
      if (!isReplan && !loggedAsSafety) {
        onPromptLog?.(submittedGoal);
      }
    }
  }, [goal, planLoading, base64Image, obstacles, userId, boardDetected, hamsterFacing, hamsterPosition, lang, onSafetyBlock, onPromptLog, onPlanGenerated, onPlanReady, t]);

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
        goal, hamsterPosition, obstacles, lang,
      );
      onCodeReady?.({ ...result, _selectedChoice: choiceId });
    } catch (e) {
      setError(e.message ?? t("plan.error.code"));
      setSelectedChoice(null);
    } finally {
      setCodeLoading(false);
    }
  }, [isCooltime, codeLoading, plan, userId, platform, boardDetected, goal, hamsterPosition, obstacles, lang, onCodeReady, onChoiceMade, runGeneratePlan, t]);

  return (
    <section className="w-full max-w-7xl mx-auto space-y-3">

      <div className="flex items-center gap-2">
        <span className="inline-flex items-center justify-center w-8 h-8 rounded-full
                         bg-sky-500 text-white font-black text-base shadow-md">2</span>
        <h2 className="text-xl font-black text-gray-800 tracking-tight">
          {t("plan.title")}
        </h2>
      </div>

      {!plan && (
        <div className="kid-card bg-white rounded-3xl shadow-xl border-4 border-sky-200 overflow-hidden">
          <div className="px-4 py-2 bg-gradient-to-r from-sky-300 to-sky-500 flex items-center gap-2">
            <img src="/mascots/goal-icon.png" alt={t("plan.goalCard.iconAlt")}
                 className="w-9 h-9 object-contain drop-shadow animate-floaty" />
            <p className="text-sm font-extrabold text-white tracking-wide">{t("plan.goalCard.title")}</p>
          </div>
          <div className="p-4 space-y-3">
            <p className="speech-bubble text-sm text-sky-800 font-semibold">
              {t("plan.goalCard.intro")}
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
                <img src="/mascots/goal-icon.png" alt={t("plan.goalCard.iconAlt")}
                     className="w-9 h-9 object-contain drop-shadow animate-floaty" />
                <p className="text-sm font-extrabold text-white tracking-wide">{t("plan.goalCard.title")}</p>
              </div>
              <div className="p-3 space-y-2">
                <p className="speech-bubble text-xs text-sky-800 font-semibold">
                  {t("plan.goalCard.intro")}
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
                <img src="/mascots/ai-hamster.png" alt={t("plan.aiPlanIconAlt")}
                     className="w-9 h-9 object-contain drop-shadow animate-floaty" />
                <p className="text-sm font-extrabold text-white tracking-wide">
                  {t("plan.aiPlanTitle")}
                  {Array.isArray(plan.steps) && plan.steps.length > 0 && t("plan.aiPlanSteps", { n: plan.steps.length })}
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
                  {t("plan.fallbackEmpty")}
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
                      {t("plan.codeLoading")}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="kid-card bg-white rounded-3xl shadow-xl border-4 border-orange-200 overflow-hidden">
                  <div className="px-4 py-2 bg-gradient-to-r from-orange-300 to-orange-500 flex items-center gap-2">
                    <img src="/mascots/trophy-kid.png" alt={t("plan.choices.iconAlt")}
                         className="w-9 h-9 object-contain drop-shadow animate-floaty" />
                    <p className="text-sm font-extrabold text-white tracking-wide">
                      {t("plan.choices.boxTitle")}
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
