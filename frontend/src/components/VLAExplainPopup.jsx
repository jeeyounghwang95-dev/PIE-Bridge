// frontend/src/components/VLAExplainPopup.jsx
//
// 단계 전환 시 VLA(Vision-Language-Action) 모델과의 연관성을 설명하는 팝업.
// 햄스터 마스코트가 말풍선으로 설명하는 형태.
// "다시 보지 않기" 체크 시 단계별로 localStorage에 저장되어 다시 표시되지 않음.

import { useT } from "../i18n/LanguageContext";

const COLOR_MAP = {
  V: "text-blue-600",
  L: "text-green-600",
  A: "text-orange-500",
};

// "{V}ision" 같은 토큰을 색상 강조 span으로 변환
function renderColored(text) {
  const parts = text.split(/(\{[VLA]\})/g);
  return parts.map((part, i) => {
    const m = part.match(/^\{([VLA])\}$/);
    if (m) {
      const letter = m[1];
      return (
        <span key={i} className={`font-black ${COLOR_MAP[letter]}`}>
          {letter}
        </span>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

const STAGE_CONTENT = {
  plan: {
    titleKey: "vla.plan.title",
    nextKey: "vla.plan.next",
    bodyKeys: [
      "vla.plan.body.p1",
      "vla.plan.body.p1tag",
      "vla.plan.body.p2",
      "vla.plan.body.p3",
      "vla.plan.body.p4",
      "vla.plan.body.p5",
      "vla.plan.body.p6",
    ],
  },
  code: {
    titleKey: "vla.code.title",
    nextKey: "vla.code.next",
    bodyKeys: [
      "vla.code.body.p1",
      "vla.code.body.p2",
      "vla.code.body.p3",
      "vla.code.body.p4",
      "vla.code.body.p5",
      "vla.code.body.p6",
      "vla.code.body.p7",
    ],
  },
};

export default function VLAExplainPopup({ stage, onClose, onDontShowAgain }) {
  const { t } = useT();
  const content = STAGE_CONTENT[stage];
  if (!content) return null;

  const handleNext = (e) => {
    const dontShow = e.currentTarget.form?.elements?.dontShow?.checked;
    if (dontShow) onDontShowAgain?.(stage);
    onClose?.();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => e.preventDefault()}
        className="relative max-w-2xl w-full"
      >
        {/* 햄스터 + 말풍선 레이아웃 */}
        <div className="flex items-end gap-3 sm:gap-4">
          {/* 햄스터 마스코트 */}
          <div className="hidden sm:flex shrink-0 w-28 h-28 rounded-full bg-gradient-to-br from-sky-200 to-sky-400 items-center justify-center shadow-xl border-4 border-white overflow-hidden">
            <img
              src="/mascots/hamster-wave.png"
              alt={t("vla.hamsterAlt")}
              className="w-full h-full object-contain"
              onError={(e) => {
                e.currentTarget.replaceWith(
                  Object.assign(document.createElement("span"), {
                    textContent: "🐹",
                    style: "font-size:3rem",
                  })
                );
              }}
            />
          </div>

          {/* 말풍선 */}
          <div className="relative flex-1 bg-white rounded-3xl shadow-2xl border-4 border-sky-200 p-5 sm:p-6">
            {/* 말풍선 꼬리 (햄스터 쪽) */}
            <div className="hidden sm:block absolute -left-3 bottom-8 w-6 h-6 bg-white border-l-4 border-b-4 border-sky-200 transform rotate-45" />

            {/* 닫기 버튼 */}
            <button
              type="button"
              onClick={onClose}
              className="absolute top-2 right-2 w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-400 hover:text-gray-700 font-bold text-lg"
              title={t("vla.close")}
              aria-label={t("vla.close")}
            >
              ✕
            </button>

            {/* 모바일용 작은 햄스터 */}
            <div className="sm:hidden flex items-center gap-2 mb-3">
              <div className="w-12 h-12 rounded-full bg-gradient-to-br from-sky-200 to-sky-400 flex items-center justify-center shadow border-2 border-white overflow-hidden shrink-0">
                <img
                  src="/mascots/hamster-wave.png"
                  alt={t("vla.hamsterAlt")}
                  className="w-full h-full object-contain"
                />
              </div>
            </div>

            {/* 제목 */}
            <h2 className="font-black text-lg sm:text-xl text-sky-700 leading-snug pr-8 mb-3">
              {t(content.titleKey)}
            </h2>

            {/* 본문 */}
            <div className="space-y-2.5 text-sm sm:text-base text-gray-700 leading-relaxed">
              {content.bodyKeys.map((key) => (
                <p key={key}>{renderColored(t(key))}</p>
              ))}
            </div>

            {/* 하단: 체크박스 + 다음 버튼 */}
            <div className="mt-5 pt-4 border-t border-sky-100 flex items-center justify-between gap-3 flex-wrap">
              <label className="inline-flex items-center gap-2 text-xs sm:text-sm text-gray-500 cursor-pointer select-none">
                <input
                  type="checkbox"
                  name="dontShow"
                  className="w-4 h-4 rounded border-gray-300 text-sky-500 focus:ring-sky-400"
                />
                <span>{t("vla.dontShowAgain")}</span>
              </label>
              <button
                type="button"
                onClick={handleNext}
                className="px-5 py-2 bg-sky-500 hover:bg-sky-600 text-white font-extrabold text-sm rounded-full shadow-md transition-colors"
              >
                {t(content.nextKey)}
              </button>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
