// frontend/src/components/TeacherDashboard.jsx
//
// 교사용 학생 활동 대시보드
// - 안전 필터 차단 횟수
// - AI 협업 옵션 선택 현황 (선택지 1~5 누적)
// - 계획/코드 생성 횟수
// - 세션 시간
// 데이터는 페이지가 열려있는 동안만 유지 (새로고침/닫기 시 초기화)

import { useState, useEffect } from "react";
import { useT } from "../i18n/LanguageContext";

const CHOICE_COLOR = {
  1: "bg-indigo-500",
  3: "bg-gray-400",
  4: "bg-amber-500",
  5: "bg-purple-500",
};

const EVAL_COLOR = {
  good: "bg-green-500",
  soso: "bg-yellow-400",
  hard: "bg-red-500",
};

const EVAL_EMOJI = {
  good: "😀",
  soso: "😐",
  hard: "😟",
};

// ── 경과 시간 포맷 ──────────────────────────────────────────
function useElapsed(startTime) {
  const { t } = useT();
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startTime) / 1000)), 1000);
    return () => clearInterval(id);
  }, [startTime]);
  const m = Math.floor(elapsed / 60);
  const s = elapsed % 60;
  return m > 0 ? t("dash.minSecFmt", { m, s }) : t("dash.secFmt", { s });
}

function ChoiceBar({ label, color, count, total }) {
  const { t } = useT();
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-600 w-20 flex-shrink-0 truncate font-bold">{label}</span>
      <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-extrabold text-gray-700 w-10 text-right flex-shrink-0">
        {count}{t("dash.countSuffix")}
      </span>
    </div>
  );
}

function StatCard({ label, value, highlight }) {
  return (
    <div className={`flex flex-col items-center justify-center p-2.5 rounded-xl border-2
      ${highlight ? "bg-red-50 border-red-300" : "bg-gray-50 border-gray-200"}`}>
      <p className={`text-xl font-black leading-none ${highlight ? "text-red-600" : "text-gray-800"}`}>
        {value}
      </p>
      <p className="text-xs text-gray-500 mt-1 text-center leading-tight font-bold">{label}</p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// 메인 컴포넌트
// ─────────────────────────────────────────────────────────────
export default function TeacherDashboard({ stats, userId }) {
  const { t, lang } = useT();
  const elapsed = useElapsed(stats.startTime);
  const totalChoices = Object.values(stats.choiceCounts).reduce((a, b) => a + b, 0);
  const evaluations = stats.evaluations ?? { good: 0, soso: 0, hard: 0 };
  const totalEvaluations = Object.values(evaluations).reduce((a, b) => a + b, 0);

  // AI 협업 점수: 선택지 1·4·5만 카운트 (3은 재도전이므로 제외)
  const collaborationChoices = [1,4,5].reduce((s, id) => s + (stats.choiceCounts[id] || 0), 0);
  const collaborationRate = stats.planCount > 0
    ? Math.round((collaborationChoices / stats.planCount) * 100)
    : 0;

  const choiceItems = [
    { id: 1, label: t("dash.choice1") },
    { id: 3, label: t("dash.choice3") },
    { id: 4, label: t("dash.choice4") },
    { id: 5, label: t("dash.choice5") },
  ];

  const evalItems = [
    { id: "good", label: t("dash.eval.good") },
    { id: "soso", label: t("dash.eval.soso") },
    { id: "hard", label: t("dash.eval.hard") },
  ];

  const safetyTimeLocale = lang === "en" ? "en-US" : "ko-KR";

  return (
    <div className="w-full bg-white rounded-2xl border-2 border-sky-100 shadow-md overflow-hidden">
      {/* 헤더 */}
      <div className="flex items-center justify-between px-3 py-2 bg-sky-500">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-extrabold text-white text-sm tracking-wide whitespace-nowrap">{t("dash.header")}</span>
          <span className="px-2 py-0.5 bg-white/20 rounded-full text-white text-[0.65rem] font-bold truncate">
            {userId}
          </span>
        </div>
        <span className="text-sky-100 text-[0.65rem] font-semibold whitespace-nowrap ml-2">{elapsed} {t("dash.elapsedSuffix")}</span>
      </div>

      <div className="p-3 space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <StatCard label={t("dash.stat.plan")} value={stats.planCount} />
          <StatCard label={t("dash.stat.code")} value={stats.codeCount} />
          <StatCard label={t("dash.stat.collab")} value={`${collaborationRate}%`} />
          <StatCard label={t("dash.stat.safety")} value={stats.safetyBlocks} highlight={stats.safetyBlocks > 0} />
        </div>

        <div className="space-y-2">
          <p className="text-xs font-extrabold text-gray-500 uppercase tracking-wide">
            {t("dash.choices.title", { n: totalChoices })}
          </p>
          <div className="space-y-1.5">
            {choiceItems.map((c) => (
              <ChoiceBar
                key={c.id}
                label={c.label}
                color={CHOICE_COLOR[c.id]}
                count={stats.choiceCounts[c.id] || 0}
                total={totalChoices}
              />
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-extrabold text-gray-500 uppercase tracking-wide">
            {t("dash.eval.title", { n: totalEvaluations })}
          </p>
          <div className="grid grid-cols-3 gap-1.5">
            {evalItems.map((m) => {
              const count = evaluations[m.id] || 0;
              const pct = totalEvaluations > 0 ? Math.round((count / totalEvaluations) * 100) : 0;
              return (
                <div
                  key={m.id}
                  className="flex flex-col items-center justify-center p-2 rounded-xl border-2 bg-gray-50 border-gray-200"
                >
                  <span className="text-2xl leading-none">{EVAL_EMOJI[m.id]}</span>
                  <p className="text-base font-black text-gray-800 mt-1 leading-none">{count}{t("dash.countSuffix")}</p>
                  <p className="text-[0.65rem] text-gray-500 font-bold mt-0.5 text-center leading-tight">{m.label}</p>
                  <div className="w-full h-1.5 bg-gray-200 rounded-full mt-1.5 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${EVAL_COLOR[m.id]}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {stats.promptLog && stats.promptLog.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs font-extrabold text-gray-500 uppercase tracking-wide">
              {t("dash.promptLog.title", { n: stats.promptLog.length })}
            </p>
            <div className="max-h-44 overflow-y-auto space-y-1">
              {stats.promptLog.slice().reverse().map((entry, i) => {
                const isSafety = entry.kind === "safety";
                const wrap = isSafety
                  ? "bg-red-50 border-red-200"
                  : "bg-green-50 border-green-200";
                const timeColor = isSafety ? "text-red-400" : "text-green-500";
                const textColor = isSafety ? "text-red-700" : "text-green-800";
                return (
                  <div key={i} className={`flex items-start gap-2 px-2 py-1.5 rounded-lg border ${wrap}`}>
                    <span className={`text-[0.65rem] flex-shrink-0 font-mono mt-0.5 ${timeColor}`}>
                      {new Date(entry.time).toLocaleTimeString(safetyTimeLocale, { hour: "2-digit", minute: "2-digit" })}
                    </span>
                    <span className={`text-xs break-all font-semibold ${textColor}`}>"{entry.input}"</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {stats.planCount === 0 && (!stats.promptLog || stats.promptLog.length === 0) && (
          <div className="text-center py-3 text-gray-400 text-xs font-semibold">
            {t("dash.empty")}
          </div>
        )}
      </div>
    </div>
  );
}
