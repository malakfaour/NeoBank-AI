"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type Locale = "en" | "ar";
type Messages = Record<string, { en: string; ar: string }>;

const messages: Messages = {
  "nav.dashboard": { en: "Dashboard", ar: "الرئيسية" },
  "nav.home": { en: "Home", ar: "الرئيسية" },
  "nav.addMoney": { en: "Add Money", ar: "إضافة أموال" },
  "nav.transfer": { en: "Transfer", ar: "تحويل الأموال" },
  "nav.beneficiaries": { en: "Beneficiaries", ar: "المستفيدون" },
  "nav.exchange": { en: "Exchange", ar: "تحويل العملات" },
  "nav.payBills": { en: "Pay Bills", ar: "دفع الفواتير" },
  "nav.transactions": { en: "Transactions", ar: "المعاملات" },
  "nav.history": { en: "History", ar: "السجل" },
  "nav.profile": { en: "Profile", ar: "الملف الشخصي" },
  "nav.aiHelp": { en: "AI Help", ar: "مساعد نيو" },
  "nav.signOut": { en: "Sign out", ar: "تسجيل الخروج" },
  "nav.login": { en: "Log in", ar: "تسجيل الدخول" },
  "nav.signup": { en: "Create account", ar: "إنشاء حساب" },
  "nav.security": { en: "Security", ar: "الأمان" },
  "nav.operations": { en: "Operations", ar: "العمليات" },
  "nav.kycReview": { en: "KYC Review", ar: "مراجعة الهوية" },
  "nav.flaggedTransactions": { en: "Flagged Transactions", ar: "المعاملات المعلّمة" },
  "nav.users": { en: "Users", ar: "المستخدمون" },
  "nav.allTransactions": { en: "All Transactions", ar: "جميع المعاملات" },
  "nav.risk": { en: "Risk", ar: "المخاطر" },
  "nav.ledger": { en: "Ledger", ar: "السجل" },

  "landing.eyebrow": { en: "Built for life in Lebanon", ar: "مصرفك الرقمي في لبنان" },
  "landing.title": { en: "Your money, moving at your pace.", ar: "أموالك بين يديك، بكل سهولة." },
  "landing.body": { en: "Spend, send, and exchange with one secure account designed for everyday life in Lebanon.", ar: "ادفع وحوّل وبدّل العملات من حساب آمن صُمّم لحياتك اليومية في لبنان." },
  "landing.trusted": { en: "Protected with bank-grade security", ar: "حماية مصرفية متقدمة" },
  "landing.section": { en: "Everything you need. Nothing you don't.", ar: "كل ما تحتاج إليه، من دون تعقيد." },
  "landing.section.body": { en: "Real banking tools, presented simply.", ar: "خدمات مصرفية حقيقية بتجربة بسيطة وواضحة." },
  "feature.wallet": { en: "One smart wallet", ar: "محفظة ذكية واحدة" },
  "feature.wallet.body": { en: "USD and LBP accounts, always clear and easy to reach.", ar: "حسابات بالدولار والليرة، واضحة وسهلة الوصول دائماً." },
  "feature.transfer": { en: "Instant transfers", ar: "تحويلات فورية" },
  "feature.transfer.body": { en: "Send money in a few taps and follow every movement.", ar: "أرسل الأموال بخطوات بسيطة وتابع كل معاملة." },
  "feature.exchange": { en: "Simple exchange", ar: "تحويل عملات بسهولة" },
  "feature.exchange.body": { en: "See the live rate before you confirm. No surprises.", ar: "اطّلع على سعر الصرف المباشر قبل التأكيد، بكل وضوح." },
  "feature.secure": { en: "Secure by design", ar: "أمان في كل خطوة" },
  "feature.secure.body": { en: "Identity checks and device protection keep you in control.", ar: "التحقق من الهوية وحماية الجهاز يبقيان حسابك تحت سيطرتك." },

  "kyc.eyebrow": { en: "Identity verification", ar: "التحقق من الهوية" },
  "kyc.title": { en: "A few things before you start", ar: "قبل أن تبدأ" },
  "kyc.body": { en: "Set aside about five minutes. Your information is encrypted and used only to verify your identity.", ar: "تحتاج العملية إلى نحو خمس دقائق. معلوماتك مشفّرة وتُستخدم فقط للتحقق من هويتك." },
  "kyc.id": { en: "A valid identity document", ar: "وثيقة هوية سارية المفعول" },
  "kyc.id.body": { en: "Lebanese ID, passport, or driving licence", ar: "هوية لبنانية أو جواز سفر أو رخصة قيادة" },
  "kyc.light": { en: "Good lighting", ar: "إضاءة جيدة" },
  "kyc.light.body": { en: "For a clear, quick selfie check", ar: "لالتقاط صورة شخصية واضحة بسرعة" },
  "kyc.internet": { en: "A stable connection", ar: "اتصال إنترنت مستقر" },
  "kyc.internet.body": { en: "So your progress saves without interruption", ar: "لحفظ تقدمك من دون انقطاع" },
  "kyc.steps": { en: "What you'll do", ar: "خطوات التحقق" },
  "kyc.step1": { en: "Personal information", ar: "المعلومات الشخصية" },
  "kyc.step2": { en: "Identity document", ar: "وثيقة الهوية" },
  "kyc.step3": { en: "Selfie verification", ar: "التحقق بالصورة الشخصية" },
  "kyc.step4": { en: "Review and submit", ar: "المراجعة والإرسال" },
  "kyc.start": { en: "Start verification", ar: "بدء التحقق" },
  "kyc.private": { en: "Your data stays private and protected", ar: "تبقى بياناتك خاصة ومحمية" },

  "header.hello": { en: "Good day", ar: "مرحباً" },
  "dashboard.available": { en: "Available balance", ar: "الرصيد المتاح" },
  "dashboard.card": { en: "Neo everyday", ar: "بطاقة نيو اليومية" },
  "dashboard.iban": { en: "Copy IBAN", ar: "نسخ رقم الآيبان" },
  "dashboard.copied": { en: "Copied", ar: "تم النسخ" },
  "dashboard.actions": { en: "Quick actions", ar: "الخدمات السريعة" },
  "dashboard.transfer": { en: "Transfer", ar: "تحويل أموال" },
  "dashboard.add": { en: "Add money", ar: "إضافة رصيد" },
  "dashboard.exchange": { en: "Exchange", ar: "صرف العملات" },
  "dashboard.bills": { en: "Pay bills", ar: "دفع الفواتير" },
  "dashboard.accounts": { en: "Your accounts", ar: "حساباتك" },
  "dashboard.recent": { en: "Recent activity", ar: "أحدث المعاملات" },
  "dashboard.view": { en: "View all", ar: "عرض الكل" },
  "dashboard.freshUsd": { en: "Fresh USD", ar: "دولار أميركي" },
  "dashboard.cashLbp": { en: "Cash LBP", ar: "ليرة لبنانية" },
  "dashboard.marketRate": { en: "Market exchange rate", ar: "سعر الصرف في السوق" },
  "dashboard.updated": { en: "Updated", ar: "آخر تحديث" },
  "dashboard.live": { en: "Live", ar: "مباشر" },
  "dashboard.spending": { en: "Spending by category", ar: "الإنفاق حسب الفئة" },
  "dashboard.noSpending": { en: "No spending data yet this month", ar: "لا توجد بيانات إنفاق لهذا الشهر بعد" },
  "dashboard.makeTransaction": { en: "Make a transaction to see your breakdown", ar: "أجرِ معاملة لعرض تفاصيل إنفاقك" },
  "dashboard.noTransactions": { en: "No transactions yet", ar: "لا توجد معاملات بعد" },

  "exchange.title": { en: "Exchange", ar: "تحويل العملات" },
  "exchange.eyebrow": { en: "Live currency desk", ar: "أسعار العملات المباشرة" },
  "exchange.hero": { en: "Exchange with clarity.", ar: "حوّل عملاتك بكل وضوح." },
  "exchange.heroBody": { en: "Convert securely between your Neo USD and LBP wallets.", ar: "حوّل بأمان بين محفظتي الدولار والليرة في نيو." },
  "exchange.marketOpen": { en: "Market open", ar: "السوق مفتوح" },
  "exchange.marketClosed": { en: "Market closed", ar: "السوق مغلق" },
  "exchange.marketHours": { en: "Trading hours are Monday–Friday, 08:00–17:00 Beirut time", ar: "ساعات التداول من الاثنين إلى الجمعة، من 08:00 حتى 17:00 بتوقيت بيروت" },
  "exchange.convertFunds": { en: "Convert funds", ar: "تحويل الأموال" },
  "exchange.choose": { en: "Choose currencies and amount", ar: "اختر العملتين والمبلغ" },
  "exchange.from": { en: "From", ar: "من" },
  "exchange.to": { en: "To", ar: "إلى" },
  "exchange.rate": { en: "Live rate", ar: "سعر الصرف المباشر" },
  "exchange.rateUnavailable": { en: "Rate unavailable", ar: "سعر الصرف غير متاح" },
  "exchange.history": { en: "USD/LBP Rate History + Forecast", ar: "حركة سعر الدولار مقابل الليرة والتوقعات" },
  "exchange.forecastNotice": { en: "Forecast is indicative only and not guaranteed.", ar: "التوقعات استرشادية فقط وليست مضمونة." },
  "exchange.historical": { en: "Historical", ar: "السعر السابق" },
  "exchange.forecast": { en: "Forecast", ar: "التوقع" },
  "exchange.stale": { en: "Stale data", ar: "البيانات غير محدّثة" },
  "exchange.preview": { en: "Preview Exchange", ar: "معاينة التحويل" },
  "exchange.loadingRate": { en: "Getting rate...", ar: "جارٍ تحميل السعر..." },
  "exchange.confirmIdentity": { en: "Confirm Identity", ar: "تأكيد الهوية" },
  "exchange.enterPasscode": { en: "Enter your passcode to confirm", ar: "أدخل رمز المرور للتأكيد" },
  "exchange.continue": { en: "Continue", ar: "متابعة" },
  "exchange.verifying": { en: "Verifying...", ar: "جارٍ التحقق..." },
  "exchange.confirm": { en: "Confirm Exchange", ar: "تأكيد التحويل" },
  "exchange.executing": { en: "Executing...", ar: "جارٍ تنفيذ التحويل..." },
  "exchange.complete": { en: "Exchange Complete!", ar: "تم تحويل العملات بنجاح" },
  "exchange.sent": { en: "Sent", ar: "المبلغ المرسل" },
  "exchange.received": { en: "Received", ar: "المبلغ المستلم" },
  "exchange.id": { en: "Exchange ID", ar: "رقم عملية التحويل" },
  "common.backDashboard": { en: "Back to Dashboard", ar: "العودة إلى الرئيسية" },
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
  return useContext(PreferencesContext);
}
