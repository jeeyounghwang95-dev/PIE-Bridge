// frontend/src/components/TeacherDashboard.jsx
//
// 교사용 학생 활동 대시보드
// - 안전 필터 차단 횟수
// - AI 협업 옵션 선택 현황 (선택지 1~5 누적)
// - 계획/코드 생성 횟수
// - 세션 시간
// 데이터는 페이지가 열려있는 동안만 유지 (새로고침/닫기 시 초기화)

import { useState, useEffect } from "react";

const CHOICE_META = [
  { id: 1, label: "이대로 실행",   color: "bg-indigo-500" },
  { id: 3, label: "다시 계획",     color: "bg-gray-400"   },
  { id: 4, label: "장애물 회피",   color: "bg-amber-500"  },
  { id: 5, label: "효율적으로",    color: "bg-purple-500" },
];

const EVAL_META = [
  { id: "good", emoji: "😀", label: "좋아요",   color: "bg-green-500"  },
  { id: "soso", emoji: "😐", label: "보통",     color: "bg-yellow-400" },
  { id: "hard", emoji: "😟", label: "아쉬워요", color: "bg-red-500"    },
];

// ── 경과 시간 포맷 ──────────────────────────────────────────
function useElapsed(startTime) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startTime) / 1000)), 1000);
    return () => clearInterval(id);
  }, [startTime]);
  const m = Math.floor(elapsed / 60);
  const s = elapsed % 60;
  return m > 0 ? `${m}분 ${s}초` : `${s}초`;
}

function ChoiceBar({ meta, count, total }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-600 w-16 flex-shrink-0 truncate font-bold">{meta.label}</span>
      <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${meta.color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-extrabold text-gray-700 w-8 text-right flex-shrink-0">
        {count}회
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
  const elapsed = useElapsed(stats.startTime);
  const totalChoices = Object.values(stats.choiceCounts).reduce((a, b) => a + b, 0);
  const evaluations = stats.evaluations ?? { good: 0, soso: 0, hard: 0 };
  const totalEvaluations = Object.values(evaluations).reduce((a, b) => a + b, 0);

  // AI 협업 점수: 선택지 1·2·4·5만 카운트 (3은 재도전이므로 제외)
  const collaborationChoices = [1,4,5].reduce((s, id) => s + (stats.choiceCounts[id] || 0), 0);
  const collaborationRate = stats.planCount > 0
    ? Math.round((collaborationChoices / stats.planCount) * 100)
    : 0;

  return (
    <div className="w-full bg-white rounded-2xl border-2 border-sky-100 shadow-md overflow-hidden">
      {/* 헤더 */}
      <div className="flex items-center justify-between px-3 py-2 bg-sky-500">
        <div className="flex items-center gap-2">
          <span className="font-extrabold text-white text-sm tracking-wide">대시보드</span>
          <span className="px-2 py-0.5 bg-white/20 rounded-full text-white text-[0.65rem] font-bold">
            {userId}
          </span>
        </div>
        <span className="text-sky-100 text-[0.65rem] font-semibold">{elapsed} 활동 중</span>
      </div>

      <div className="p-3 space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <StatCard label="계획 생성" value={stats.planCount} />
          <StatCard label="코드 생성" value={stats.codeCount} />
          <StatCard label="AI 협업률" value={`${collaborationRate}%`} />
          <StatCard label="안전 차단" value={stats.safetyBlocks} highlight={stats.safetyBlocks > 0} />
        </div>

        <div className="space-y-2">
          <p className="text-xs font-extrabold text-gray-500 uppercase tracking-wide">
            AI 협업 옵션 선택 현황 (총 {totalChoices}회)
          </p>
          <div className="space-y-1.5">
            {CHOICE_META.map((meta) => (
              <ChoiceBar
                key={meta.id}
                meta={meta}
                count={stats.choiceCounts[meta.id] || 0}
                total={totalChoices}
              />
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-extrabold text-gray-500 uppercase tracking-wide">
            계획 평가 (SMILE FACE · 총 {totalEvaluations}회)
          </p>
          <div className="grid grid-cols-3 gap-1.5">
            {EVAL_META.map((m) => {
              const count = evaluations[m.id] || 0;
              const pct = totalEvaluations > 0 ? Math.round((count / totalEvaluations) * 100) : 0;
              return (
                <div
                  key={m.id}
                  className="flex flex-col items-center justify-center p-2 rounded-xl border-2 bg-gray-50 border-gray-200"
                >
                  <span className="text-2xl leading-none">{m.emoji}</span>
                  <p className="text-base font-black text-gray-800 mt-1 leading-none">{count}회</p>
                  <p className="text-[0.65rem] text-gray-500 font-bold mt-0.5">{m.label}</p>
                  <div className="w-full h-1.5 bg-gray-200 rounded-full mt-1.5 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${m.color}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {stats.safetyBlocks > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs font-extrabold text-gray-500 uppercase tracking-wide">
              안전 필터 차단 기록
            </p>
            <div className="max-h-28 overflow-y-auto space-y-1">
              {stats.safetyLog.slice().reverse().map((entry, i) => (
                <div key={i} className="flex items-start gap-2 px-2 py-1.5 bg-red-50 rounded-lg border border-red-200">
                  <span className="text-[0.65rem] text-red-400 flex-shrink-0 font-mono mt-0.5">
                    {new Date(entry.time).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                  <span className="text-xs text-red-700 break-all font-semibold">"{entry.input}"</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {stats.planCount === 0 && stats.safetyBlocks === 0 && (
          <div className="text-center py-3 text-gray-400 text-xs font-semibold">
            아직 활동이 없어요. 학생이 사진을 찍으면 여기에 기록돼요.
          </div>
        )}
      </div>
    </div>
  );
}
