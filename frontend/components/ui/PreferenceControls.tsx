"use client";

import { usePreferences } from "@/components/providers/AppPreferences";

export default function PreferenceControls({ compact = false }: { compact?: boolean }) {
  const { locale, setLocale } = usePreferences();
  return (
    <div className="preference-controls" aria-label="Display preferences">
      <button
        type="button"
        className="preference-language"
        onClick={() => setLocale(locale === "en" ? "ar" : "en")}
        aria-label={locale === "en" ? "Switch to Arabic" : "Switch to English"}
      >
        {compact ? (locale === "en" ? "AR" : "EN") : (locale === "en" ? "العربية" : "English")}
      </button>
    </div>
  );
}
