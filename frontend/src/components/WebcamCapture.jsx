// frontend/src/components/WebcamCapture.jsx
//
// PIE BRIDGE - 웹캠 캡처 + 이미지 리사이징 + 품질 검사 컴포넌트
//
// 전체 흐름:
//   1. 카메라 권한 요청 → 실시간 미리보기 스트림
//   2. [사진 찍기] 클릭 → canvas 에서 800px 리사이징 후 base64 추출
//   3. analyzeImage() 호출 → AI 품질 검사 (Flash 모델)
//   4-A. 합격 → 학생이 분석 결과를 검토/수정 → onCaptureReady 콜백으로 부모 전달
//   4-B. 불합격 → "다시 찍어요" UI 표시 및 재시도

import { useState, useRef, useEffect, useCallback } from "react";
import { analyzeImage } from "../services/api";
import { useT } from "../i18n/LanguageContext";

const RESIZE_MAX_WIDTH  = 800;
const CAPTURE_QUALITY   = 0.85;
const PREVIEW_ASPECT    = "4/3";

// ── 카메라 권한 에러 안내 ────────────────────────────────────
function PermissionError({ onRetry }) {
  const { t } = useT();
  return (
    <div className="flex flex-col items-center gap-4 py-10 text-center px-6">
      <div>
        <p className="font-bold text-gray-700 text-lg">{t("capture.permission.title")}</p>
        <p
          className="text-gray-500 text-sm mt-1 leading-relaxed"
          dangerouslySetInnerHTML={{ __html: t("capture.permission.body").replace(/\n/g, "<br />") }}
        />
      </div>
      <button
        onClick={onRetry}
        className="px-5 py-2.5 bg-sky-500 hover:bg-sky-600 text-white
                   font-bold rounded-xl transition-colors shadow-sm"
      >
        {t("capture.permission.retry")}
      </button>
    </div>
  );
}

// ── 분석 결과 카드 (편집 가능) ────────────────────────────────
function QualityResultCard({ result, editable, onChange, onRetake, onConfirm, mode }) {
  const { t } = useT();
  const hamsterMissing = result?.hamster_detected === false;
  const passed = result?.passed && !hamsterMissing;
  const retakeLabel  = mode === "upload" ? t("capture.retake.upload") : t("capture.retake.camera");
  const failHeadline = mode === "upload" ? t("capture.fail.upload") : t("capture.fail.camera");
  const hamsterHint  = mode === "upload"
    ? t("capture.hamsterMissing.upload")
    : t("capture.hamsterMissing.camera");

  const updateObstacle = (idx, field, value) => {
    const next = (editable.obstacles || []).map((o, i) => i === idx ? { ...o, [field]: value } : o);
    onChange({ ...editable, obstacles: next });
  };
  const removeObstacle = (idx) => {
    const next = (editable.obstacles || []).filter((_, i) => i !== idx);
    onChange({ ...editable, obstacles: next });
  };
  const addObstacle = () => {
    const next = [...(editable.obstacles || []), { name: "", position: "" }];
    onChange({ ...editable, obstacles: next });
  };

  return (
    <div className={`
      w-full p-3 rounded-2xl shadow-md space-y-2 border-2
      ${passed ? "bg-green-50 border-green-300" : "bg-red-50 border-red-300"}
    `}>
      <div className="flex items-center gap-2">
        <p className={`font-black text-base ${passed ? "text-green-800" : "text-red-800"}`}>
          {passed ? t("capture.passed") : failHeadline}
        </p>
      </div>
      <p className={`text-xs leading-snug font-semibold ${passed  ? "text-green-700" : "text-red-700"}`}>
        {hamsterMissing ? hamsterHint : result?.reason}
      </p>

      {/* 합격 시: 편집 가능한 분석 결과 */}
      {passed && (
        <div className="space-y-2 bg-white/70 rounded-xl p-2.5 border-2 border-green-200">
          <p className="text-xs font-extrabold text-green-800">
            {t("capture.editable.title")}
          </p>

          <div className="space-y-1">
            <label className="text-xs font-extrabold text-gray-600">
              {t("capture.editable.hamsterPosition")}
            </label>
            <input
              type="text"
              value={editable.hamsterPosition ?? ""}
              onChange={(e) => onChange({ ...editable, hamsterPosition: e.target.value })}
              placeholder={t("capture.editable.hamsterPosition.placeholder")}
              className="w-full px-2.5 py-1.5 text-xs border-2 border-gray-300 rounded-lg
                         focus:outline-none focus:ring-2 focus:ring-green-300 font-semibold"
            />
          </div>

          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="text-xs font-extrabold text-gray-600">
                {t("capture.editable.obstacles")}
              </label>
              <button
                type="button"
                onClick={addObstacle}
                className="text-xs font-extrabold text-green-700 hover:text-green-900
                           border-2 border-green-300 rounded-full px-2 py-0.5 bg-white whitespace-nowrap"
              >
                {t("capture.editable.addObstacle")}
              </button>
            </div>
            {(editable.obstacles?.length ?? 0) === 0 ? (
              <p className="text-xs text-gray-500 italic font-semibold">
                {t("capture.editable.noObstacles")}
              </p>
            ) : (
              <div className="space-y-1 max-h-32 overflow-y-auto pr-1">
                {editable.obstacles.map((obs, i) => (
                  <div key={i} className="flex gap-1 items-center">
                    <input
                      type="text"
                      value={obs.name ?? ""}
                      onChange={(e) => updateObstacle(i, "name", e.target.value)}
                      placeholder={t("capture.editable.obstacleName.placeholder")}
                      className="w-1/3 px-2 py-1 text-xs border-2 border-gray-300 rounded-lg
                                 focus:outline-none focus:ring-2 focus:ring-green-300 font-semibold"
                    />
                    <input
                      type="text"
                      value={obs.position ?? ""}
                      onChange={(e) => updateObstacle(i, "position", e.target.value)}
                      placeholder={t("capture.editable.obstaclePosition.placeholder")}
                      className="flex-1 px-2 py-1 text-xs border-2 border-gray-300 rounded-lg
                                 focus:outline-none focus:ring-2 focus:ring-green-300 font-semibold"
                    />
                    <button
                      type="button"
                      onClick={() => removeObstacle(i)}
                      className="text-xs font-extrabold text-red-500 hover:text-red-700 px-1.5 whitespace-nowrap"
                      title={t("capture.editable.removeObstacleTitle")}
                    >
                      {t("capture.editable.removeObstacle")}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <input
              id="board-detected-edit"
              type="checkbox"
              checked={!!editable.boardDetected}
              onChange={(e) => onChange({ ...editable, boardDetected: e.target.checked })}
              className="w-4 h-4 accent-green-600"
            />
            <label htmlFor="board-detected-edit" className="text-xs font-extrabold text-gray-700">
              {t("capture.editable.boardDetected")}
            </label>
          </div>
        </div>
      )}

      <div className="flex gap-2 pt-1">
        <button
          onClick={onRetake}
          className="flex-1 py-2 bg-white border-2 border-gray-300 hover:bg-gray-50
                     text-gray-700 font-extrabold text-sm rounded-xl transition-colors"
        >
          {retakeLabel}
        </button>
        {passed && (
          <button
            onClick={onConfirm}
            className="flex-1 py-2 bg-sky-500 hover:bg-sky-600
                       text-white font-extrabold text-sm rounded-xl transition-colors shadow-md"
          >
            {t("capture.confirm")}
          </button>
        )}
      </div>
    </div>
  );
}

// ── 분석 중 오버레이 ─────────────────────────────────────────
function AnalyzingOverlay() {
  const { t } = useT();
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center
                    bg-black/50 rounded-2xl gap-4">
      <div className="w-14 h-14 border-4 border-white/30 border-t-white rounded-full animate-spin" />
      <p className="text-white font-bold text-lg drop-shadow animate-pulse">
        {t("capture.analyzing")}
      </p>
    </div>
  );
}

// ── 카메라 전환 버튼 ─────────────────────────────────────────
function CameraFlipButton({ onClick }) {
  const { t } = useT();
  return (
    <button
      onClick={onClick}
      className="absolute top-3 right-3 px-3 h-9 bg-black/40 hover:bg-black/60
                 text-white rounded-full flex items-center justify-center
                 text-xs font-bold transition-colors z-10 whitespace-nowrap"
      title={t("capture.cameraFlip")}
    >
      {t("capture.cameraFlip")}
    </button>
  );
}

// ─────────────────────────────────────────────────────────────
// 이미지 리사이징 유틸리티
// ─────────────────────────────────────────────────────────────

function captureAndResize(video, maxWidth = RESIZE_MAX_WIDTH, quality = CAPTURE_QUALITY) {
  const canvas = document.createElement("canvas");
  const sourceW = video.videoWidth;
  const sourceH = video.videoHeight;
  const scale  = sourceW > maxWidth ? maxWidth / sourceW : 1;
  canvas.width  = Math.round(sourceW * scale);
  canvas.height = Math.round(sourceH * scale);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", quality);
}

function imageToResizedBase64(img, maxWidth = RESIZE_MAX_WIDTH, quality = CAPTURE_QUALITY) {
  const canvas = document.createElement("canvas");
  const sourceW = img.naturalWidth;
  const sourceH = img.naturalHeight;
  const scale  = sourceW > maxWidth ? maxWidth / sourceW : 1;
  canvas.width  = Math.round(sourceW * scale);
  canvas.height = Math.round(sourceH * scale);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", quality);
}

function readFileAsResizedBase64(file, errMsgs) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(errMsgs.fileRead));
    reader.onload = (e) => {
      const img = new Image();
      img.onerror = () => reject(new Error(errMsgs.readFile));
      img.onload  = () => resolve(imageToResizedBase64(img));
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  });
}

function toEditable(result) {
  const obstacles = (result?.obstacles_detected ?? []).map((o) => {
    if (typeof o === "string") return { name: o, position: "" };
    return { name: o?.name ?? "", position: o?.position ?? "" };
  });
  return {
    hamsterPosition: result?.hamster_position ?? "",
    obstacles,
    boardDetected: !!result?.board_detected,
  };
}


// ─────────────────────────────────────────────────────────────
// 메인 컴포넌트: WebcamCapture
// ─────────────────────────────────────────────────────────────

export default function WebcamCapture({ userId = "anonymous", onCaptureReady }) {
  const { t, lang } = useT();
  const [mode, setMode]                 = useState("camera");
  const [robotConnected, setRobotConnected] = useState(false);
  const [streamReady, setStreamReady]   = useState(false);
  const [permissionErr, setPermErr]     = useState(false);
  const [facingMode, setFacingMode]     = useState("environment");
  const [capturedBase64, setCaptured]   = useState(null);
  const [analyzing, setAnalyzing]       = useState(false);
  const [qualityResult, setQResult]     = useState(null);
  const [editable, setEditable]         = useState(null);
  const [error, setError]               = useState("");
  const [isDragging, setIsDragging]     = useState(false);

  const videoRef  = useRef(null);
  const streamRef = useRef(null);
  const fileInputRef = useRef(null);


  const startCamera = useCallback(async () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }

    setStreamReady(false);
    setPermErr(false);
    setError("");
    setCaptured(null);
    setQResult(null);
    setEditable(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode,
          width:  { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => setStreamReady(true);
      }
    } catch (err) {
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        setPermErr(true);
      } else {
        setError(t("capture.error.camera"));
      }
    }
  }, [facingMode, t]);

  useEffect(() => {
    if (!robotConnected || mode !== "camera") {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setStreamReady(false);
      return;
    }
    startCamera();
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [robotConnected, startCamera, mode]);

  const analyzeBase64 = useCallback(async (base64) => {
    setAnalyzing(true);
    try {
      const result = await analyzeImage(base64, userId, lang);
      setQResult(result);
      setEditable(toEditable(result));
    } catch (e) {
      setError(e.message ?? t("capture.error.analyze"));
      streamRef.current?.getTracks().forEach((track) => { track.enabled = true; });
    } finally {
      setAnalyzing(false);
    }
  }, [userId, lang, t]);

  const handleCapture = useCallback(async () => {
    if (!videoRef.current || !streamReady || analyzing) return;
    setError("");
    setQResult(null);
    setEditable(null);
    const base64 = captureAndResize(videoRef.current);
    setCaptured(base64);
    streamRef.current?.getTracks().forEach((track) => { track.enabled = false; });
    await analyzeBase64(base64);
  }, [streamReady, analyzing, analyzeBase64]);

  const handleFileSelect = useCallback(async (file) => {
    if (!file || analyzing) return;
    if (!file.type.startsWith("image/")) {
      setError(t("capture.error.imageOnly"));
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError(t("capture.error.tooLarge"));
      return;
    }
    setError("");
    setQResult(null);
    setEditable(null);
    try {
      const base64 = await readFileAsResizedBase64(file, {
        fileRead: t("capture.error.fileRead"),
        readFile: t("capture.error.readFile"),
      });
      setCaptured(base64);
      await analyzeBase64(base64);
    } catch (e) {
      setError(e.message ?? t("capture.error.readFile"));
    }
  }, [analyzing, analyzeBase64, t]);

  const handleFileInputChange = useCallback((e) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
    e.target.value = "";
  }, [handleFileSelect]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileSelect(file);
  }, [handleFileSelect]);

  const handleModeChange = useCallback((newMode) => {
    if (newMode === mode) return;
    setMode(newMode);
    setCaptured(null);
    setQResult(null);
    setEditable(null);
    setError("");
  }, [mode]);

  const handleRetake = useCallback(() => {
    setCaptured(null);
    setQResult(null);
    setEditable(null);
    setError("");
    streamRef.current?.getTracks().forEach((track) => { track.enabled = true; });
  }, []);

  const handleFlip = useCallback(() => {
    setFacingMode((prev) => (prev === "environment" ? "user" : "environment"));
  }, []);

  const handleConfirm = useCallback(() => {
    if (!capturedBase64 || !qualityResult?.passed || !editable) return;
    const obstacles = [...(editable.obstacles ?? [])].filter(o => (o.name || "").trim());
    onCaptureReady?.(
      capturedBase64,
      obstacles,
      !!editable.boardDetected,
      qualityResult.hamster_facing ?? "unknown",
      editable.hamsterPosition ?? "",
    );
  }, [capturedBase64, qualityResult, editable, onCaptureReady]);

  if (permissionErr) {
    return (
      <section className="w-full max-w-md mx-auto bg-white rounded-2xl shadow-md overflow-hidden">
        <PermissionError onRetry={startCamera} />
      </section>
    );
  }

  // 좌우 분할 모드: 분석 결과가 도착했을 때
  const showSideBySide = !!qualityResult && !analyzing && !!editable;

  // ── 카메라/업로드 뷰파인더 ──
  const viewfinderStyle = showSideBySide
    ? { aspectRatio: PREVIEW_ASPECT, maxHeight: "65vh", width: "100%" }
    : { aspectRatio: PREVIEW_ASPECT, maxHeight: "60vh", maxWidth: "calc(60vh * 4 / 3)" };

  const Viewfinder = (
    <>
      {mode === "camera" && (
        <div
          className="relative bg-black rounded-xl overflow-hidden shadow-lg mx-auto"
          style={viewfinderStyle}
        >
          {!robotConnected && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-gray-900">
              <p className="text-white/80 font-bold text-base text-center px-6">
                {t("capture.viewfinder.connectFirst")}
              </p>
            </div>
          )}
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className={`
              w-full h-full object-cover
              ${capturedBase64 ? "hidden" : "block"}
            `}
          />
          {capturedBase64 && (
            <img
              src={capturedBase64}
              alt={t("capture.captured.alt")}
              className="w-full h-full object-cover"
            />
          )}
          {!streamReady && !capturedBase64 && robotConnected && (
            <div className="absolute inset-0 flex flex-col items-center justify-center
                            bg-gray-900 gap-3">
              <div className="w-10 h-10 border-4 border-white/20 border-t-white
                              rounded-full animate-spin" />
              <p className="text-white/70 text-sm">{t("capture.cameraReady")}</p>
            </div>
          )}
          {analyzing && <AnalyzingOverlay />}
          {streamReady && !capturedBase64 && !analyzing && (
            <CameraFlipButton onClick={handleFlip} />
          )}
          {streamReady && !capturedBase64 && (
            <div className="absolute inset-0 pointer-events-none">
              <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2
                              w-16 h-16 border-2 border-white/30 rounded-lg" />
            </div>
          )}
        </div>
      )}

      {mode === "upload" && (
        <div
          className="relative bg-black rounded-xl overflow-hidden shadow-lg mx-auto"
          style={viewfinderStyle}
        >
          {capturedBase64 ? (
            <>
              <img
                src={capturedBase64}
                alt={t("capture.uploaded.alt")}
                className="w-full h-full object-cover"
              />
              {analyzing && <AnalyzingOverlay />}
            </>
          ) : (
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => robotConnected && fileInputRef.current?.click()}
              className={`
                absolute inset-0 flex flex-col items-center justify-center gap-3
                border-4 border-dashed transition-colors
                ${!robotConnected
                  ? "bg-gray-900 border-gray-700 cursor-not-allowed"
                  : isDragging
                    ? "bg-sky-900/40 border-sky-400 cursor-pointer"
                    : "bg-gray-800 border-gray-600 hover:bg-gray-700 cursor-pointer"}
              `}
            >
              {!robotConnected ? (
                <p className="text-white/80 font-bold text-base text-center px-6">
                  {t("capture.viewfinder.connectFirst")}
                </p>
              ) : (
                <>
                  <p className="text-white font-bold text-base text-center px-4">
                    {t("capture.upload.dropOrClick")}
                  </p>
                  <p className="text-white/60 text-xs">
                    {t("capture.upload.formats")}
                  </p>
                </>
              )}
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileInputChange}
            className="hidden"
          />
        </div>
      )}
    </>
  );

  // ── 캡처/업로드 후 안내 (콤팩트) ──
  const NoticeBlock = capturedBase64 ? (
    <div className="px-3 py-2 bg-sky-50 border-2 border-sky-200
                    rounded-xl text-xs text-sky-800 font-semibold">
      <p className="leading-snug">
        <strong>{t("capture.notice.warning")}</strong>{" "}
        {mode === "camera" ? t("capture.notice.camera") : t("capture.notice.upload")}
      </p>
    </div>
  ) : null;

  return (
    <section className="w-full max-w-6xl mx-auto space-y-2">

      <div className="flex items-center gap-2 flex-wrap">
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full
                         bg-sky-500 text-white font-black text-base shadow-md">1</span>
        <h2 className="text-xl font-black text-gray-800 tracking-tight">
          {t("capture.title")}
        </h2>
        <a
          href="https://robomationlab.com/BlockComposer/"
          target="_blank"
          rel="noopener noreferrer"
          className="ml-2 inline-flex items-center gap-1.5 px-3 py-1 rounded-full
                     bg-white border-2 border-sky-200 hover:border-sky-400 hover:bg-sky-50
                     text-sky-700 font-extrabold text-xs shadow-sm transition-colors whitespace-nowrap"
          title={t("capture.robomationLinkTitle")}
        >
          <img
            src="/robomation-icon.png"
            alt=""
            className="w-5 h-5 rounded-full"
          />
          <span>{t("capture.robomationLink")}</span>
          <span aria-hidden="true" className="text-sky-400">↗</span>
        </a>
      </div>
      <p className="text-xs text-gray-500 -mt-1 font-semibold">
        {t("capture.subtitle")}
      </p>

      {/* 1열: 모드 탭 */}
      <div className="grid grid-cols-2 gap-1 p-0 bg-gray-100 rounded-xl">
        {[
          { id: "camera", label: t("capture.tab.camera") },
          { id: "upload", label: t("capture.tab.upload") },
        ].map((m) => (
          <button
            key={m.id}
            onClick={() => handleModeChange(m.id)}
            className={`
              py-2 rounded-lg font-extrabold text-sm transition-all
              flex items-center justify-center
              ${mode === m.id
                ? "bg-white text-sky-600 shadow-md"
                : "text-gray-600 hover:text-gray-800"}
            `}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* 2열: 로봇 연결 체크 (가운데 정렬, 내용에 맞춰 폭 자동) */}
      <div className="flex justify-center">
        <label className={`
          inline-flex items-center gap-2 px-4 py-1.5 rounded-xl border-2 cursor-pointer select-none
          transition-colors max-w-full
          ${robotConnected
            ? "bg-green-50 border-green-300 text-green-800"
            : "bg-amber-50 border-amber-300 text-amber-800"}
        `}>
          <input
            type="checkbox"
            checked={robotConnected}
            onChange={(e) => setRobotConnected(e.target.checked)}
            className="w-4 h-4 accent-green-600 flex-shrink-0"
          />
          <span className="font-extrabold text-[clamp(0.7rem,1vw,0.95rem)] leading-tight text-center">
            {robotConnected
              ? t("capture.robotConnected")
              : t("capture.robotCheck")}
          </span>
        </label>
      </div>

      {/* 메인 영역: 분석 결과가 있으면 좌우 분할, 없으면 단일 컬럼 */}
      {showSideBySide ? (
        <div className="flex flex-row gap-3 items-start">
          {/* 왼쪽: 캡처된 이미지 + 안내 */}
          <div className="w-1/2 space-y-2">
            {Viewfinder}
            {NoticeBlock}
          </div>
          {/* 오른쪽: 분석 결과 카드 */}
          <div className="w-1/2">
            <QualityResultCard
              result={qualityResult}
              editable={editable}
              onChange={setEditable}
              onRetake={handleRetake}
              onConfirm={handleConfirm}
              mode={mode}
            />
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          {Viewfinder}
          {NoticeBlock}
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 px-4 py-2 bg-red-50 border border-red-200
                        rounded-xl text-sm text-red-700">
          <span className="flex-1">{error}</span>
          <button
            onClick={handleRetake}
            className="px-3 py-1 bg-red-100 hover:bg-red-200 text-red-700
                       font-bold rounded-lg text-xs transition-colors shrink-0"
          >
            {t("capture.retake.camera")}
          </button>
        </div>
      )}

      {!capturedBase64 && mode === "camera" && (
        <button
          onClick={handleCapture}
          disabled={!streamReady || analyzing || !robotConnected}
          className="
            w-full py-3 bg-sky-500 hover:bg-sky-600
            disabled:bg-gray-300 disabled:cursor-not-allowed
            text-white font-black text-lg rounded-2xl
            transition-all duration-150 active:scale-[0.98]
            shadow-md hover:shadow-xl
            flex items-center justify-center gap-3
          "
        >
          {robotConnected ? t("capture.captureBtn") : t("capture.captureBtn.disabled")}
        </button>
      )}
      {!capturedBase64 && mode === "upload" && (
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={analyzing || !robotConnected}
          className="
            w-full py-3 bg-sky-500 hover:bg-sky-600
            disabled:bg-gray-300 disabled:cursor-not-allowed
            text-white font-black text-lg rounded-2xl
            transition-all duration-150 active:scale-[0.98]
            shadow-md hover:shadow-xl
            flex items-center justify-center gap-3
          "
        >
          {robotConnected ? t("capture.uploadBtn") : t("capture.uploadBtn.disabled")}
        </button>
      )}
    </section>
  );
}
