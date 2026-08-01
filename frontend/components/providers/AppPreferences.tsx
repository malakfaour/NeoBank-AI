"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type Locale = "en" | "ar";

type Messages = Record<string, { en: string; ar: string }>;

const messages: Messages = {
  "nav.login": { en: "Log in", ar: "تسجيل الدخول" },
  "nav.signup": { en: "Create account", ar: "إنشاء حساب" },
  "nav.security": { en: "Security", ar: "الأمان" },
  "landing.eyebrow": { en: "Built for life in Lebanon", ar: "مصرفك الرقمي في لبنان" },
  "landing.title": { en: "Your money, moving at your pace.", ar: "أموالك، تتحرك على إيقاعك." },
  "landing.body": { en: "Spend, send, and exchange with one secure account designed for everyday life in Lebanon.", ar: "ادفع وحوّل وبدّل العملات من حساب آمن واحد مصمم لحياتك اليومية في لبنان." },
  "landing.trusted": { en: "Protected with bank-grade security", ar: "محمي بأمان بمستوى مصرفي" },
  "feature.wallet": { en: "One smart wallet", ar: "محفظة ذكية واحدة" },
  "feature.wallet.body": { en: "USD and LBP accounts, always clear and easy to reach.", ar: "حسابات بالدولار والليرة، واضحة وسهلة الوصول دائماً." },
  "feature.transfer": { en: "Instant transfers", ar: "تحويلات فورية" },
  "feature.transfer.body": { en: "Send money in a few taps and follow every movement.", ar: "أرسل الأموال بخطوات قليلة وتابع كل حركة." },
  "feature.exchange": { en: "Simple exchange", ar: "تبديل عملات بسيط" },
  "feature.exchange.body": { en: "See the live rate before you confirm. No surprises.", ar: "شاهد السعر المباشر قبل التأكيد. بلا مفاجآت." },
  "feature.secure": { en: "Secure by design", ar: "أمان من الأساس" },
  "feature.secure.body": { en: "Identity checks and device protection keep you in control.", ar: "التحقق من الهوية وحماية الجهاز يبقيانك مسيطراً." },
  "landing.section": { en: "Everything you need. Nothing you don't.", ar: "كل ما تحتاجه. من دون تعقيد." },
  "landing.section.body": { en: "Real banking tools, presented simply.", ar: "أدوات مصرفية حقيقية، بتجربة بسيطة." },
  "kyc.eyebrow": { en: "Identity verification", ar: "التحقق من الهوية" },
  "kyc.title": { en: "A few things before you start", ar: "بعض الأمور قبل أن تبدأ" },
  "kyc.body": { en: "Set aside about five minutes. Your information is encrypted and used only to verify your identity.", ar: "خصص نحو خمس دقائق. معلوماتك مشفّرة وتُستخدم فقط للتحقق من هويتك." },
  "kyc.id": { en: "A valid identity document", ar: "وثيقة هوية سارية" },
  "kyc.id.body": { en: "Lebanese ID, passport, or driving licence", ar: "هوية لبنانية أو جواز سفر أو رخصة قيادة" },
  "kyc.light": { en: "Good lighting", ar: "إضاءة جيدة" },
  "kyc.light.body": { en: "For a clear, quick selfie check", ar: "لالتقاط صورة شخصية واضحة وسريعة" },
  "kyc.internet": { en: "A stable connection", ar: "اتصال إنترنت مستقر" },
  "kyc.internet.body": { en: "So your progress saves without interruption", ar: "لحفظ تقدمك من دون انقطاع" },
  "kyc.steps": { en: "What you'll do", ar: "ما ستقوم به" },
  "kyc.step1": { en: "Personal information", ar: "المعلومات الشخصية" },
  "kyc.step2": { en: "Identity document", ar: "وثيقة الهوية" },
  "kyc.step3": { en: "Selfie verification", ar: "التحقق بالصورة الشخصية" },
  "kyc.step4": { en: "Review and submit", ar: "المراجعة والإرسال" },
  "kyc.start": { en: "Start verification", ar: "ابدأ التحقق" },
  "kyc.private": { en: "Your data stays private and protected", ar: "تبقى بياناتك خاصة ومحمية" },
  "dashboard.available": { en: "Available balance", ar: "الرصيد المتاح" },
  "dashboard.card": { en: "Neo everyday", ar: "بطاقة نيو اليومية" },
  "dashboard.iban": { en: "Copy IBAN", ar: "نسخ رقم IBAN" },
  "dashboard.copied": { en: "Copied", ar: "تم النسخ" },
  "dashboard.actions": { en: "Quick actions", ar: "إجراءات سريعة" },
  "dashboard.transfer": { en: "Transfer", ar: "تحويل" },
  "dashboard.add": { en: "Add money", ar: "إضافة أموال" },
  "dashboard.exchange": { en: "Exchange", ar: "تبديل" },
  "dashboard.bills": { en: "Pay bills", ar: "دفع الفواتير" },
  "dashboard.accounts": { en: "Your accounts", ar: "حساباتك" },
  "dashboard.recent": { en: "Recent activity", ar: "النشاط الأخير" },
  "dashboard.view": { en: "View all", ar: "عرض الكل" },
  "header.hello": { en: "Good day", ar: "مرحباً" },
};

interface PreferencesValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string) => string;
}

const translate = (key: string, locale: Locale) => messages[key]?.[locale] ?? key;

const PreferencesContext = createContext<PreferencesValue>({
  locale: "en",
  setLocale: () => undefined,
  t: (key) => translate(key, "en"),
});

export function AppPreferences({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const savedLocale = localStorage.getItem("neo-locale") as Locale | null;
      if (savedLocale === "ar" || savedLocale === "en") setLocaleState(savedLocale);
      localStorage.removeItem("neo-theme");
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
    delete document.documentElement.dataset.theme;
  }, [locale]);

  const value = useMemo<PreferencesValue>(() => ({
    locale,
    setLocale: (next) => {
      setLocaleState(next);
      localStorage.setItem("neo-locale", next);
    },
    t: (key) => translate(key, locale),
  }), [locale]);

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences() {
  const value = useContext(PreferencesContext);
  return value;
}
