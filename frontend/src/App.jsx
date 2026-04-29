// frontend/src/App.jsx

import { useState } from "react";
import WebcamCapture    from "./components/WebcamCapture";
import ChatAndPlan      from "./components/ChatAndPlan";
import CodeViewer       from "./components/CodeViewer";
import TeacherDashboard from "./components/TeacherDashboard";

const USER_ID = "student_001";

// ── 단계 진행 표시 바 ────────────────────────────────────────
const STAGE_STEPS = [
  { id: "capture", label: "1. 사진 찍기" },
  { id: "plan",    label: "2. 계획 세우기" },
  { id: "code",    label: "3. 코드 받기" },
];

function ProgressBar({ currentStage }) {
  const currentIdx = STAGE_STEPS.findIndex((s) => s.id === currentStage);
  return (
    <div className="flex items-center justify-center gap-1 py-1">
      {STAGE_STEPS.map((step, i) => {
        const isDone    = i < currentIdx;
        const isCurrent = i === currentIdx;
        return (
          <div key={step.id} className="flex items-center gap-1">
            <div className={`
              flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-extrabold
              transition-all duration-300 border-2
              ${isCurrent ? "bg-sky-500 text-white border-sky-500 shadow-md scale-105" : ""}
              ${isDone    ? "bg-green-100 text-green-700 border-green-200" : ""}
              ${!isCurrent && !isDone ? "bg-white text-gray-400 border-gray-200" : ""}
            `}>
              <span>{step.label}</span>
            </div>
            {i < STAGE_STEPS.length - 1 && (
              <div className={`w-4 h-1 rounded-full transition-colors duration-300
                               ${i < currentIdx ? "bg-green-300" : "bg-gray-200"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── stats 초기값 ─────────────────────────────────────────────
function initStats() {
  return {
    safetyBlocks: 0,
    safetyLog: [],
    planCount: 0,
    codeCount: 0,
    choiceCounts: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 },
    startTime: Date.now(),
  };
}

// ─────────────────────────────────────────────────────────────
export default function App() {
  const [platform]                        = useState("robomation");
  const [stage, setStage]                 = useState("capture");
  const [capturedImage, setCapturedImage] = useState(null);
  const [obstacles, setObstacles]         = useState([]);
  const [hamsterPosition, setHamsterPosition] = useState("");
  const [boardDetected, setBoardDetected] = useState(false);
  const [hamsterFacing, setHamsterFacing] = useState("unknown");
  const [codeResult, setCodeResult]       = useState(null);
  const [codeLoading, setCodeLoading]     = useState(false);
  const [currentPlan, setCurrentPlan]     = useState(null);
  const [goal, setGoal]                   = useState("");
  const [stats, setStats]                 = useState(initStats);
  const [isDashboardOpen, setIsDashboardOpen] = useState(false);

  const addSafetyBlock = (input) => setStats((s) => ({
    ...s,
    safetyBlocks: s.safetyBlocks + 1,
    safetyLog: [...s.safetyLog, { time: Date.now(), input }],
  }));
  const addPlan    = () => setStats((s) => ({ ...s, planCount:  s.planCount  + 1 }));
  const addCode    = () => setStats((s) => ({ ...s, codeCount:  s.codeCount  + 1 }));
  const addChoice  = (id) => setStats((s) => ({
    ...s,
    choiceCounts: { ...s.choiceCounts, [id]: (s.choiceCounts[id] || 0) + 1 },
  }));

  const handleCaptureReady = (base64, detectedObstacles, detectedBoard, detectedFacing, detectedHamsterPos) => {
    setCapturedImage(base64);
    setObstacles(detectedObstacles);
    setHamsterPosition(detectedHamsterPos ?? "");
    setBoardDetected(detectedBoard ?? false);
    setHamsterFacing(detectedFacing ?? "unknown");
    setCodeResult(null);
    setCurrentPlan(null);
    setStage("plan");
  };

  const handleCodeReady = (result) => {
    setCodeResult(result);
    addCode();
    setStage("code");
  };

  const handlePlanReady = (plan) => {
    setCurrentPlan(plan);
  };

  const handleResetToStart = () => {
    setCapturedImage(null);
    setObstacles([]);
    setHamsterPosition("");
    setCodeResult(null);
    setCurrentPlan(null);
    setGoal("");
    setStage("capture");
  };

  return (
    <div className="min-h-screen bg-sky-50">

      {/* ── 헤더 ── */}
      <header className="sticky top-0 z-20 bg-white/90 backdrop-blur-sm
                          border-b border-sky-100 shadow-sm">
        <div className="max-w-screen-2xl mx-auto px-5">
          <div className="flex items-center justify-between py-2">
            <button
              type="button"
              onClick={handleResetToStart}
              className="flex items-center gap-2 group cursor-pointer focus:outline-none
                         focus-visible:ring-2 focus-visible:ring-sky-300 rounded-lg"
              title="처음 페이지로 돌아가기"
            >
              <div className="w-9 h-9 rounded-2xl bg-gradient-to-br from-sky-300 to-sky-500
                              flex items-center justify-center
                              shadow-md text-white text-2xl font-black overflow-hidden
                              transition-transform group-hover:scale-110 group-hover:rotate-3">
                <img
                  src="/mascots/hamster-wave.png"
                  alt="햄스터봇"
                  className="w-full h-full object-contain"
                  onError={(e) => { e.currentTarget.replaceWith(Object.assign(document.createElement('span'), { textContent: '🐹' })); }}
                />
              </div>
              <div className="text-left">
                <h1 className="font-black text-xl text-sky-600 leading-none tracking-tight
                               group-hover:text-sky-700 transition-colors">PIE BRIDGE</h1>
                <p className="text-xs text-gray-400 leading-none mt-1">
                  블록코딩에서 파이썬 AI코딩으로
                </p>
              </div>
            </button>

            <div className="flex-1 flex justify-center">
              <ProgressBar currentStage={stage} />
            </div>

            <div className="flex items-center gap-2">
              {stage !== "capture" && (
                <button
                  onClick={handleResetToStart}
                  className="px-4 py-1.5 text-xs font-extrabold text-sky-600
                             hover:bg-sky-50 rounded-full transition-colors border-2 border-sky-100"
                >
                  처음으로
                </button>
              )}
              <button
                onClick={() => setIsDashboardOpen((v) => !v)}
                className={`
                  px-4 py-1.5 text-xs font-extrabold rounded-full
                  transition-colors border-2 inline-flex items-center gap-1.5
                  ${isDashboardOpen
                    ? "bg-sky-500 text-white border-sky-500 shadow-md"
                    : "text-sky-600 hover:bg-sky-50 border-sky-100"}
                `}
                title="교사 대시보드 열기/닫기"
              >
                <span>📊</span>
                <span>대시보드</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* ── 메인 콘텐츠 (대시보드와 같은 레이아웃 줄을 공유하지 않음) ── */}
      <div className="px-5 py-4 mx-auto max-w-screen-2xl">
        <main className="w-full space-y-4">
          {stage === "capture" && (
            <WebcamCapture
              userId={USER_ID}
              onCaptureReady={handleCaptureReady}
            />
          )}

          {stage === "plan" && (
            <ChatAndPlan
              base64Image={capturedImage}
              obstacles={obstacles}
              hamsterPosition={hamsterPosition}
              userId={USER_ID}
              platform={platform}
              boardDetected={boardDetected}
              hamsterFacing={hamsterFacing}
              goal={goal}
              onGoalChange={setGoal}
              onCodeReady={handleCodeReady}
              onPlanReady={handlePlanReady}
              onSafetyBlock={addSafetyBlock}
              onPlanGenerated={addPlan}
              onChoiceMade={addChoice}
            />
          )}

          {stage === "code" && (
            <>
              <CodeViewer
                isLoading={codeLoading}
                explanation={codeResult?.explanation}
                pythonCode={codeResult?.python_code}
                safetyBlocked={codeResult?.blocked}
                safetyMessage={codeResult?.message}
                replan={codeResult?.replan}
                selectedChoice={codeResult?._selectedChoice}
                boardDetected={boardDetected}
                originalPlan={currentPlan}
                planChanged={codeResult?.plan_changed ?? false}
                changeReason={codeResult?.change_reason ?? ""}
                modifiedSteps={codeResult?.modified_steps ?? []}
              />
              {!codeLoading && (
                <div className="flex justify-center">
                  <button
                    onClick={() => setStage("plan")}
                    className="px-8 py-4 border-2 border-sky-200 hover:bg-sky-50
                               text-sky-700 font-extrabold text-lg rounded-full transition-colors shadow-sm"
                  >
                    ← 다른 방법으로 다시 해볼게요
                  </button>
                </div>
              )}
            </>
          )}
        </main>
      </div>

      {/* ── 교사 대시보드 (오른쪽 슬라이드 패널) ── */}
      {/* 백드롭 */}
      <div
        onClick={() => setIsDashboardOpen(false)}
        className={`
          fixed inset-0 bg-black/30 z-30 transition-opacity duration-300
          ${isDashboardOpen ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"}
        `}
      />
      {/* 패널 */}
      <aside
        className={`
          fixed top-0 right-0 h-full w-80 xl:w-96 z-40
          bg-white shadow-2xl border-l-2 border-sky-100
          transition-transform duration-300 ease-out
          flex flex-col
          ${isDashboardOpen ? "translate-x-0" : "translate-x-full"}
        `}
      >
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-sky-100 flex-shrink-0">
          <span className="font-black text-sm text-sky-700">교사 대시보드</span>
          <button
            onClick={() => setIsDashboardOpen(false)}
            className="w-7 h-7 flex items-center justify-center rounded-full
                       hover:bg-gray-100 text-gray-500 font-bold"
            title="닫기"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          <TeacherDashboard stats={stats} userId={USER_ID} />
        </div>
      </aside>

      {/* ── 푸터 ── */}
      <footer className="text-center py-3 text-xs text-gray-400">
        PIE BRIDGE · © JeeyoungHwang/SNUE
      </footer>
    </div>
  );
}
