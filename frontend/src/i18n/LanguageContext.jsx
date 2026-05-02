// frontend/src/i18n/LanguageContext.jsx
//
// 사이트 전체의 언어 상태(ko/en)를 관리한다.
// localStorage 에 사용자의 선택을 보존하고, useT() 훅으로 번역 함수를 제공한다.

import { createContext, useContext, useState, useEffect, useCallback, useMemo } from "react";
import { translations, format } from "./translations";

const STORAGE_KEY = "pie_bridge_lang";
const DEFAULT_LANG = "ko";

const LanguageContext = createContext({
  lang: DEFAULT_LANG,
  setLang: () => {},
  t: (key) => key,
});

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(() => {
    if (typeof window === "undefined") return DEFAULT_LANG;
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved === "ko" || saved === "en" ? saved : DEFAULT_LANG;
  });

  const setLang = useCallback((next) => {
    if (next !== "ko" && next !== "en") return;
    setLangState(next);
    try { window.localStorage.setItem(STORAGE_KEY, next); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = lang;
    }
  }, [lang]);

  const t = useCallback((key, vars) => {
    const dict = translations[lang] || translations[DEFAULT_LANG];
    const tpl = dict[key] ?? translations[DEFAULT_LANG][key] ?? key;
    return vars ? format(tpl, vars) : tpl;
  }, [lang]);

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useT() {
  return useContext(LanguageContext);
}
