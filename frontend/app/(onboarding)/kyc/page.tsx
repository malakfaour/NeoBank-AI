"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";
import SelfieCapture from "@/components/kyc/SelfieCapture";
import { usePreferences } from "@/components/providers/AppPreferences";
import { ArrowRight, Check, ChevronDown, Eye, ScanFace, SunMedium, UserRound } from "lucide-react";
import PreferenceControls from "@/components/ui/PreferenceControls";

type Profile = Record<string, string>;
type Workflow = "not_started" | "in_progress" | "pending" | "approved" | "rejected";
export type KYCDocumentType = "national_id" | "passport" | "drivers_license";

export function buildKycUploadForm(
  files: { front: File; back?: File },
  documentType: KYCDocumentType,
) {
  const form = new FormData();
  form.append("id_photo", files.front);
  if (files.back) form.append("back_id_photo", files.back);
  form.append("document_type", documentType);
  form.append("submit_for_review", "false");
  return form;
}

// Passports are a single photo page - only national IDs and driver's
// licenses have a meaningful back side to capture.
function requiresBackPage(identificationType: string | undefined): boolean {
  return identificationType !== "passport";
}

export function buildKycSelfieForm(selfie: File) {
  const form = new FormData();
  form.append("selfie", selfie);
  return form;
}

export function DocumentTypeSelection({
  selected, onSelect, onBack, onContinue,
}: {
  selected: KYCDocumentType | null;
  onSelect: (value: KYCDocumentType) => void;
  onBack: () => void;
  onContinue: () => void;
}) {
  return <section>
    <div style={{ display: "grid", gap: 10 }}>
      {([
        ["national_id", "National ID"],
        ["passport", "Passport"],
      ] as const).map(([value, label]) => (
        <button key={value} type="button" aria-pressed={selected === value} onClick={() => onSelect(value)}>
          {label}
        </button>
      ))}
    </div>
    <button type="button" onClick={onBack}>Back</button>
    <button type="button" onClick={onContinue} disabled={!selected}>Continue</button>
  </section>;
}

interface KYCResponse {
  workflow_status: Workflow;
  current_step: number;
  profile_data: Profile;
  has_front_id: boolean;
  has_back_id: boolean;
  has_selfie: boolean;
  rejection_reason?: string | null;
}

interface Field {
  key: string;
  label: string;
  type?: string;
  required?: boolean;
  options?: string[];
}

const steps: { title: string; subtitle: string; fields: Field[] }[] = [
  {
    title: "Personal information",
    subtitle: "Tell us about yourself exactly as shown on your identification.",
    fields: [
      { key: "first_name", label: "First name", required: true },
      { key: "fathers_name", label: "Father’s name", required: true },
      { key: "mothers_name", label: "Mother’s name", required: true },
      { key: "last_name", label: "Last name", required: true },
      { key: "date_of_birth", label: "Date of birth", type: "date", required: true },
      { key: "place_of_birth", label: "Place of birth", required: true },
      { key: "gender", label: "Gender", options: ["female", "male", "other"], required: true },
      { key: "marital_status", label: "Marital status", options: ["single", "married", "divorced", "widowed"], required: true },
      { key: "nationality", label: "Nationality", required: true },
      { key: "other_nationality", label: "Other nationality" },
    ],
  },
  {
    title: "Residential address",
    subtitle: "Enter your primary place of residence.",
    fields: [
      { key: "country_of_residence", label: "Country of residence", required: true },
      { key: "governorate", label: "Governorate", required: true },
      { key: "district", label: "District", required: true },
      { key: "state", label: "State (where applicable)" },
      { key: "city", label: "City", required: true },
      { key: "street", label: "Street", required: true },
      { key: "building", label: "Building", required: true },
      { key: "floor", label: "Floor" },
      { key: "neighbourhood", label: "Neighbourhood" },
      { key: "residential_address", label: "Full residential address", required: true },
    ],
  },
  {
    title: "Employment information",
    subtitle: "Employment details help us meet regulatory requirements.",
    fields: [
      { key: "occupation", label: "Employment status", options: ["employee", "business_owner", "student", "unemployed"], required: true },
      { key: "employer_name", label: "Employer or business name" },
      { key: "position", label: "Rank or position" },
      { key: "employment_address", label: "Employment or business address" },
      { key: "employer_phone", label: "Employer phone", type: "tel" },
      { key: "education_institution", label: "University or school" },
    ],
  },
  {
    title: "Financial information",
    subtitle: "This information is confidential and used for compliance.",
    fields: [
      { key: "source_of_funds", label: "Source of funds", options: ["salary", "business", "savings", "family_support", "other"], required: true },
      { key: "annual_income_usd", label: "Annual income (USD)", type: "number", required: true },
      { key: "other_source_of_income", label: "Other source of income" },
    ],
  },
  {
    title: "Selfie verification",
    subtitle: "Capture a live selfie so we can verify that it is really you.",
    fields: [],
  },
  {
    title: "Identification and document upload",
    subtitle: "Provide current identification, review your details, and submit.",
    fields: [
      { key: "identification_type", label: "Identification type", options: ["national_id", "passport", "drivers_license"], required: true },
      { key: "identification_number", label: "Identification number", required: true },
      { key: "record_number", label: "Record number" },
      { key: "register_place", label: "Register place" },
      { key: "id_expiry_date", label: "ID expiry date", type: "date", required: true },
    ],
  },
];

export function getKycResumeStep(data: KYCResponse) {
  const hasAll = (keys: string[]) => keys.every(
    (key) => String(data.profile_data[key] ?? "").trim(),
  );
  if (!hasAll(steps[0].fields.filter((field) => field.required).map((field) => field.key))) return 1;
  if (!hasAll(steps[1].fields.filter((field) => field.required).map((field) => field.key))) return 2;
  if (!hasAll(["occupation"])) return 3;
  if (
    data.profile_data.occupation === "employee"
    && !hasAll(["employer_name", "position", "employment_address", "employer_phone"])
  ) return 3;
  if (!hasAll(steps[3].fields.filter((field) => field.required).map((field) => field.key))) return 4;
  if (!data.has_selfie) return 5;
  const identificationComplete = steps[5].fields
    .filter((field) => field.required)
    .every((field) => String(data.profile_data[field.key] ?? "").trim());
  const backPageComplete = !requiresBackPage(data.profile_data.identification_type) || data.has_back_id;
  if (!identificationComplete || !data.has_front_id || !backPageComplete) return 6;
  return Math.min(Math.max(data.current_step || 6, 1), 6);
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "12px 14px", borderRadius: "12px",
  border: "1px solid #E5E7EB", background: "#fff", color: "#111",
};

function KycSelect({
  label, value, options, placeholder, getOptionLabel, onChange,
}: {
  label: string;
  value: string;
  options: string[];
  placeholder: string;
  getOptionLabel: (option: string) => string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  return (
    <div className={`kyc-select${open ? " is-open" : ""}`} ref={rootRef}>
      <button
        type="button"
        className="kyc-select__trigger"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}
      >
        <span className={value ? "" : "is-placeholder"}>{value ? getOptionLabel(value) : placeholder}</span>
        <ChevronDown size={18} />
      </button>
      {open && (
        <div className="kyc-select__menu" role="listbox" aria-label={label}>
          {options.map((option) => (
            <button
              type="button"
              role="option"
              aria-selected={value === option}
              className={value === option ? "is-selected" : ""}
              key={option}
              onClick={() => { onChange(option); setOpen(false); }}
            >
              <span>{getOptionLabel(option)}</span>
              {value === option && <Check size={17} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function KycDateField({
  label, value, locale, mode, onChange,
}: {
  label: string;
  value: string;
  locale: "en" | "ar";
  mode: "birth" | "expiry";
  onChange: (value: string) => void;
}) {
  const parts = /^\d{4}-\d{2}-\d{2}$/.test(value) ? value.split("-") : ["", "", ""];
  const [year, setYear] = useState(parts[0]);
  const [month, setMonth] = useState(parts[1]);
  const [day, setDay] = useState(parts[2]);
  const currentYear = new Date().getFullYear();
  const years = Array.from(
    { length: mode === "birth" ? currentYear - 1899 : 31 },
    (_, index) => String(mode === "birth" ? currentYear - index : currentYear + index),
  );
  const months = Array.from({ length: 12 }, (_, index) => String(index + 1).padStart(2, "0"));
  const availableDays = new Date(Number(year || currentYear), Number(month || 1), 0).getDate();
  const days = Array.from({ length: availableDays }, (_, index) => String(index + 1).padStart(2, "0"));
  const monthLabel = (option: string) => new Intl.DateTimeFormat(locale === "ar" ? "ar-LB" : "en-GB", { month: "short" }).format(new Date(2024, Number(option) - 1, 1));

  const update = (part: "day" | "month" | "year", nextValue: string) => {
    const nextYear = part === "year" ? nextValue : year;
    const nextMonth = part === "month" ? nextValue : month;
    let nextDay = part === "day" ? nextValue : day;
    const maxDay = new Date(Number(nextYear || currentYear), Number(nextMonth || 1), 0).getDate();
    if (Number(nextDay) > maxDay) nextDay = "";
    setYear(nextYear);
    setMonth(nextMonth);
    setDay(nextDay);
    onChange(nextYear && nextMonth && nextDay ? `${nextYear}-${nextMonth}-${nextDay}` : "");
  };

  return (
    <div className="kyc-date-field" role="group" aria-label={label}>
      <KycSelect
        label={locale === "ar" ? "اليوم" : "Day"}
        value={day}
        options={days}
        placeholder={locale === "ar" ? "اليوم" : "Day"}
        getOptionLabel={(option) => option}
        onChange={(next) => update("day", next)}
      />
      <KycSelect
        label={locale === "ar" ? "الشهر" : "Month"}
        value={month}
        options={months}
        placeholder={locale === "ar" ? "الشهر" : "Month"}
        getOptionLabel={monthLabel}
        onChange={(next) => update("month", next)}
      />
      <KycSelect
        label={locale === "ar" ? "السنة" : "Year"}
        value={year}
        options={years}
        placeholder={locale === "ar" ? "السنة" : "Year"}
        getOptionLabel={(option) => option}
        onChange={(next) => update("year", next)}
      />
    </div>
  );
}

const multipartRequestConfig = {
  headers: { "Content-Type": "multipart/form-data" },
};

export default function KYCPage() {
  const router = useRouter();
  const { locale } = usePreferences();
  const tr = (en: string, ar: string) => locale === "ar" ? ar : en;
  const arabicSteps = [
    ["المعلومات الشخصية", "أدخل معلوماتك كما تظهر تماماً على وثيقة هويتك."],
    ["عنوان السكن", "أدخل عنوان إقامتك الأساسي."],
    ["معلومات العمل", "تساعدنا معلومات العمل على استيفاء المتطلبات التنظيمية."],
    ["المعلومات المالية", "هذه المعلومات سرية وتُستخدم لأغراض الامتثال."],
    ["التحقق بصورة شخصية", "التقط صورة شخصية مباشرة للتحقق من هويتك."],
    ["الهوية ورفع المستندات", "أدخل بيانات الهوية، راجع معلوماتك، ثم أرسل الطلب."],
  ];
  const fieldLabel = (field: Field) => locale === "ar" ? ({
    first_name: "الاسم الأول", fathers_name: "اسم الأب", mothers_name: "اسم الأم", last_name: "اسم العائلة",
    date_of_birth: "تاريخ الميلاد", place_of_birth: "مكان الميلاد", gender: "الجنس", marital_status: "الحالة الاجتماعية",
    nationality: "الجنسية", other_nationality: "جنسية أخرى", country_of_residence: "بلد الإقامة", governorate: "المحافظة",
    district: "القضاء", state: "الولاية (إن وجدت)", city: "المدينة", street: "الشارع", building: "المبنى", floor: "الطابق",
    neighbourhood: "الحي", residential_address: "عنوان السكن الكامل", occupation: "الحالة الوظيفية", employer_name: "اسم جهة العمل أو الشركة",
    position: "المنصب", employment_address: "عنوان العمل", employer_phone: "هاتف جهة العمل", education_institution: "الجامعة أو المدرسة",
    source_of_funds: "مصدر الأموال", annual_income_usd: "الدخل السنوي (دولار)", other_source_of_income: "مصدر دخل آخر",
    identification_type: "نوع وثيقة الهوية", identification_number: "رقم وثيقة الهوية", record_number: "رقم السجل",
    register_place: "مكان السجل", id_expiry_date: "تاريخ انتهاء الهوية",
  } as Record<string, string>)[field.key] ?? field.label : field.label;
  const optionLabel = (option: string) => locale === "ar" ? ({ female: "أنثى", male: "ذكر", other: "آخر", single: "أعزب/عزباء", married: "متزوج/ة", divorced: "مطلق/ة", widowed: "أرمل/ة", employee: "موظف", business_owner: "صاحب عمل", student: "طالب", unemployed: "غير موظف", salary: "راتب", business: "عمل خاص", savings: "مدخرات", family_support: "دعم عائلي", national_id: "هوية لبنانية", passport: "جواز سفر", drivers_license: "رخصة قيادة" } as Record<string, string>)[option] ?? option.replaceAll("_", " ") : option.replaceAll("_", " ");
  const authUser = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const [step, setStep] = useState(1);
  const [profile, setProfile] = useState<Profile>({});
  const [workflow, setWorkflow] = useState<Workflow>("not_started");
  const [documents, setDocuments] = useState({ front: false, back: false, selfie: false });
  const [files, setFiles] = useState<{ front?: File; back?: File; selfie?: File }>({});
  const [consents, setConsents] = useState({ terms: false, correct: false, privacy: false });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [rejectionReason, setRejectionReason] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showSelfieInstructions, setShowSelfieInstructions] = useState(false);

  useEffect(() => {
    api.get<KYCResponse>("/kyc/profile").then(({ data }) => {
      setProfile(data.profile_data ?? {});
      const resumeStep = getKycResumeStep(data);
      setStep(resumeStep);
      setShowSelfieInstructions(resumeStep === 5 && !data.has_selfie);
      setWorkflow(data.workflow_status);
      setDocuments({ front: data.has_front_id, back: data.has_back_id, selfie: data.has_selfie });
      setRejectionReason(data.rejection_reason ?? null);
    }).catch(() => setMessage("Unable to load your profile. Please try again."))
      .finally(() => setLoading(false));
  }, []);

  const visibleFields = useMemo(() => {
    const fields = steps[step - 1].fields;
    if (step !== 3) return fields;
    return fields.filter((field) => {
      if (["employer_name", "employment_address"].includes(field.key)) {
        return ["employee", "business_owner"].includes(profile.occupation);
      }
      if (["position", "employer_phone"].includes(field.key)) return profile.occupation === "employee";
      if (field.key === "education_institution") return profile.occupation === "student";
      return true;
    });
  }, [profile.occupation, step]);

  const validateStep = () => {
    const nextErrors: Record<string, string> = {};
    visibleFields.forEach((field) => {
      if (field.required && !String(profile[field.key] ?? "").trim()) nextErrors[field.key] = tr(`${field.label} is required.`, `حقل ${fieldLabel(field)} مطلوب.`);
    });
    if (step === 3 && profile.occupation === "employee") {
      visibleFields
        .filter((field) => ["employer_name", "position", "employment_address", "employer_phone"].includes(field.key))
        .forEach((field) => {
          if (!String(profile[field.key] ?? "").trim()) nextErrors[field.key] = tr(`${field.label} is required.`, `حقل ${fieldLabel(field)} مطلوب.`);
        });
    }
    if (step === 5) {
      if (!documents.selfie && !files.selfie) nextErrors.selfie = tr("Selfie is required.", "الصورة الشخصية مطلوبة.");
    }
    if (step === 6) {
      if (!documents.front && !files.front) nextErrors.front = tr("Front ID image is required.", "صورة الجهة الأمامية للهوية مطلوبة.");
      if (requiresBackPage(profile.identification_type) && !documents.back && !files.back) {
        nextErrors.back = tr("Back ID image is required.", "صورة الجهة الخلفية للهوية مطلوبة.");
      }
    }
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const saveDraft = async (targetStep = step) => {
    if (step === 5 && files.selfie) {
      await api.post(
        "/kyc/selfie",
        buildKycSelfieForm(files.selfie),
        multipartRequestConfig,
      );
      setDocuments((current) => ({ ...current, selfie: true }));
    }
    if (step === 6 && files.front) {
      const form = buildKycUploadForm(
        { front: files.front, back: files.back },
        (profile.identification_type as KYCDocumentType) || "national_id",
      );
      await api.post("/kyc/upload", form, multipartRequestConfig);
      setDocuments((current) => ({ ...current, front: true, back: current.back || Boolean(files.back) }));
    }
    await api.put("/kyc/profile", { current_step: targetStep, profile_data: profile });
  };

  const next = async () => {
    if (!validateStep()) return;
    setSaving(true);
    setMessage("");
    try {
      const target = Math.min(step + 1, 6);
      await saveDraft(target);
      setStep(target);
      if (target === 5 && !documents.selfie && !files.selfie) setShowSelfieInstructions(true);
    } catch {
      setMessage(tr("We could not save your progress. Please try again.", "تعذّر حفظ تقدمك. حاول مجدداً."));
    } finally {
      setSaving(false);
    }
  };

  const submit = async () => {
    if (!validateStep()) return;
    if (!consents.terms || !consents.correct || !consents.privacy) {
      setMessage(tr("Accept all confirmations before submitting.", "وافق على جميع التأكيدات قبل إرسال الطلب."));
      return;
    }
    setSaving(true);
    try {
      await saveDraft(6);
      await api.post("/kyc/submit", {
        terms_accepted: consents.terms,
        information_confirmed: consents.correct,
        privacy_consent: consents.privacy,
      });
      setWorkflow("pending");
      if (authUser) setUser({ ...authUser, kyc_status: "pending" });
    } catch (error: unknown) {
      const fields = (error as { response?: { data?: { detail?: { fields?: string[] } } } })
        .response?.data?.detail?.fields;
      setMessage(fields?.length
        ? tr(`Missing: ${fields.join(", ")}`, `حقول ناقصة: ${fields.join("، ")}`)
        : tr("Submission failed. Review the form and try again.", "تعذّر إرسال الطلب. راجع النموذج وحاول مجدداً."));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <main className="kyc-flow-page" style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>{tr("Loading profile...", "جارٍ تحميل الملف...")}</main>;
  if (workflow === "approved" || workflow === "pending") return (
    <main className="kyc-flow-page" style={{ minHeight: "100vh", background: "var(--bg)", display: "grid", placeItems: "center", padding: 20 }}>
      <section style={{ maxWidth: 520, background: "#fff", padding: 32, borderRadius: 24, textAlign: "center" }}>
        <h1>{workflow === "approved" ? tr("Identity verified", "تم التحقق من الهوية") : tr("We're reviewing your documents", "نراجع مستنداتك الآن")}</h1>
        <p style={{ color: "#666" }}>{workflow === "approved" ? tr("Your full NeoBank access is unlocked.", "أصبحت جميع خدمات نيو متاحة لك.") : tr("Your selfie and ID have been submitted for manual review. This usually takes 2–4 business days. Transfers, Currency Exchange, and Top Ups will be available after approval.", "تم إرسال الصورة الشخصية والهوية للمراجعة. تستغرق العملية عادةً من يومين إلى أربعة أيام عمل، وستتوفر التحويلات والصرف وإضافة الأموال بعد الموافقة.")}</p>
        <button onClick={() => router.push("/dashboard")} style={{ ...inputStyle, marginTop: 20, background: "#00C853", color: "#fff", border: 0, fontWeight: 700 }}>{tr("Back to dashboard", "العودة إلى لوحة التحكم")}</button>
      </section>
    </main>
  );

  return (
    <main className="kyc-flow-page" style={{ minHeight: "100vh", background: "var(--bg)", padding: "24px 16px" }}>
      <header className="kyc-flow-toolbar">
        <div className="kyc-flow-toolbar__language">
          <PreferenceControls compact />
        </div>
      </header>
      <section style={{ maxWidth: 760, margin: "0 auto", background: "#fff", padding: 28, borderRadius: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 24 }}>
          {steps.map((_, index) => <div key={index} style={{ height: 6, flex: 1, borderRadius: 99, background: index < step ? "#00C853" : "#E5E7EB" }} />)}
        </div>
        {workflow === "rejected" && <div role="alert" style={{ background: "#FEF2F2", color: "#991B1B", padding: 14, borderRadius: 12, marginBottom: 18 }}>{tr("Your verification needs attention.", "يجب مراجعة طلب التحقق.")} {rejectionReason || tr("Review and update the requested information.", "راجع المعلومات المطلوبة وحدّثها.")}</div>}
        <p style={{ color: "#00A844", fontWeight: 700, fontSize: 13 }}>{locale === "ar" ? `الخطوة ${step} من 6` : `STEP ${step} OF 6`}</p>
        <h1 style={{ margin: "4px 0" }}>
          {step === 5 && showSelfieInstructions
            ? tr("Before we open the camera", "قبل تشغيل الكاميرا")
            : locale === "ar" ? arabicSteps[step - 1][0] : steps[step - 1].title}
        </h1>
        <p style={{ color: "#777", marginBottom: 24 }}>
          {step === 5 && showSelfieInstructions
            ? tr("A clear selfie helps us verify your identity securely and quickly.", "تساعدنا الصورة الواضحة على التحقق من هويتك بسرعة وأمان.")
            : locale === "ar" ? arabicSteps[step - 1][1] : steps[step - 1].subtitle}
        </p>
        {message && <div role="alert" style={{ color: "#B91C1C", background: "#FEF2F2", padding: 12, borderRadius: 10, marginBottom: 16 }}>{message}</div>}

        {step === 5 && showSelfieInstructions ? (
          <section className="kyc-selfie-intro">
            <div className="kyc-selfie-intro__visual" aria-hidden="true">
              <span><ScanFace size={42} /></span>
              <div className="kyc-selfie-intro__frame"><UserRound size={54} /></div>
              <small>{tr("Your face stays inside this guide", "ضع وجهك داخل هذا الإطار")}</small>
            </div>
            <div className="kyc-selfie-intro__content">
              <p className="kyc-selfie-intro__eyebrow">{tr("SELFIE CHECK", "التحقق بالصورة")}</p>
              <h2>{tr("For the best result", "للحصول على أفضل نتيجة")}</h2>
              <div className="kyc-selfie-checks">
                {[
                  { icon: Eye, en: "Look directly at the camera", ar: "انظر مباشرة إلى الكاميرا" },
                  { icon: SunMedium, en: "Use a bright, even light", ar: "استخدم إضاءة واضحة ومتوازنة" },
                  { icon: UserRound, en: "Remove glasses and face coverings", ar: "انزع النظارات وأي غطاء للوجه" },
                ].map(({ icon: Icon, en, ar }) => (
                  <div key={en}><span><Icon size={19} /></span><p>{tr(en, ar)}</p><Check size={17} /></div>
                ))}
              </div>
              <p className="kyc-selfie-intro__privacy">
                {tr("Your photo is encrypted and used only for identity verification.", "صورتك مشفّرة وتُستخدم فقط للتحقق من الهوية.")}
              </p>
            </div>
          </section>
        ) : step === 5 ? (
          <div style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 600 }}>
            {tr("Selfie", "الصورة الشخصية")} *
            <SelfieCapture
              capturedSelfie={files.selfie}
              hasSavedSelfie={documents.selfie}
              onCapture={(selfie) => {
                setFiles((current) => ({ ...current, selfie }));
                setErrors((current) => ({ ...current, selfie: "" }));
              }}
              onRetake={() => setFiles((current) => {
                const remaining = { ...current };
                delete remaining.selfie;
                return remaining;
              })}
            />
            {errors.selfie && <span style={{ color: "#B91C1C", fontWeight: 400 }}>{errors.selfie}</span>}
          </div>
        ) : step === 6 ? (
          <>
            <p style={{ fontSize: 13, fontWeight: 700, color: "#000", marginBottom: 12 }}>{tr("Identification details", "بيانات الهوية")}</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 16, marginBottom: 28 }}>
              {visibleFields.map((field) => <label key={field.key} style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 600 }}>
                {fieldLabel(field)}{field.required ? " *" : ""}
                {field.options ? <KycSelect
                  label={fieldLabel(field)}
                  value={profile[field.key] ?? ""}
                  options={field.options}
                  placeholder={tr("Choose an option", "اختر من القائمة")}
                  getOptionLabel={optionLabel}
                  onChange={(value) => setProfile({ ...profile, [field.key]: value })}
                /> : field.type === "date" ? <KycDateField
                  label={fieldLabel(field)}
                  value={profile[field.key] ?? ""}
                  locale={locale}
                  mode={field.key === "date_of_birth" ? "birth" : "expiry"}
                  onChange={(value) => setProfile({ ...profile, [field.key]: value })}
                /> : <input className="kyc-field-input" type={field.type || "text"} value={profile[field.key] ?? ""} onChange={(e) => setProfile({ ...profile, [field.key]: e.target.value })} style={inputStyle} />}
                {errors[field.key] && <span style={{ color: "#B91C1C", fontWeight: 400 }}>{errors[field.key]}</span>}
              </label>)}
            </div>

            <p style={{ fontSize: 13, fontWeight: 700, color: "#000", marginBottom: 4 }}>{tr("Upload documents", "رفع المستندات")}</p>
            <p style={{ fontSize: 12, color: "#999", marginBottom: 12 }}>
              {requiresBackPage(profile.identification_type)
                ? tr("Photograph both sides of your ID.", "صوّر الجهتين الأمامية والخلفية للهوية.")
                : tr("Photograph the photo page of your passport.", "صوّر صفحة الصورة في جواز السفر.")}
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 16 }}>
              <label style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 600 }}>
                {requiresBackPage(profile.identification_type) ? tr("Front ID image", "صورة الجهة الأمامية للهوية") : tr("Passport photo page", "صفحة الصورة في جواز السفر")} *
                <input className="kyc-field-input" type="file" accept="image/jpeg,image/png" onChange={(e) => setFiles({ ...files, front: e.target.files?.[0] })} style={inputStyle} />
                {documents.front && !files.front && <span style={{ color: "#00A844" }}>{tr("Already uploaded", "تم الرفع مسبقاً")}</span>}
                {errors.front && <span style={{ color: "#B91C1C", fontWeight: 400 }}>{errors.front}</span>}
              </label>
              {requiresBackPage(profile.identification_type) && (
                <label style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 600 }}>
                  {tr("Back ID image", "صورة الجهة الخلفية للهوية")} *
                  <input className="kyc-field-input" type="file" accept="image/jpeg,image/png" onChange={(e) => setFiles({ ...files, back: e.target.files?.[0] })} style={inputStyle} />
                  {documents.back && !files.back && <span style={{ color: "#00A844" }}>{tr("Already uploaded", "تم الرفع مسبقاً")}</span>}
                  {errors.back && <span style={{ color: "#B91C1C", fontWeight: 400 }}>{errors.back}</span>}
                </label>
              )}
            </div>
          </>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 16 }}>
            {visibleFields.map((field) => <label key={field.key} style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 600 }}>
              {fieldLabel(field)}{field.required ? " *" : ""}
              {field.options ? <KycSelect
                label={fieldLabel(field)}
                value={profile[field.key] ?? ""}
                options={field.options}
                placeholder={tr("Choose an option", "اختر من القائمة")}
                getOptionLabel={optionLabel}
                onChange={(value) => setProfile({ ...profile, [field.key]: value })}
              /> : field.type === "date" ? <KycDateField
                label={fieldLabel(field)}
                value={profile[field.key] ?? ""}
                locale={locale}
                mode={field.key === "date_of_birth" ? "birth" : "expiry"}
                onChange={(value) => setProfile({ ...profile, [field.key]: value })}
              /> : <input className="kyc-field-input" type={field.type || "text"} value={profile[field.key] ?? ""} onChange={(e) => setProfile({ ...profile, [field.key]: e.target.value })} style={inputStyle} />}
              {errors[field.key] && <span style={{ color: "#B91C1C", fontWeight: 400 }}>{errors[field.key]}</span>}
            </label>)}
          </div>
        )}

        {step === 6 && <>
          <div style={{ display: "grid", gap: 12, marginBottom: 20 }}>
            {[...steps.slice(0, 4), steps[5]].map((section) => <details key={section.title} style={{ border: "1px solid #E5E7EB", borderRadius: 12, padding: 14 }}>
              <summary style={{ fontWeight: 700, cursor: "pointer" }}>{section.title}</summary>
              {section.fields.filter((field) => profile[field.key]).map((field) => <p key={field.key} style={{ color: "#666", fontSize: 13 }}><strong>{field.label}:</strong> {field.key === "identification_number" ? `••••${profile[field.key].slice(-4)}` : profile[field.key]}</p>)}
            </details>)}
          </div>
          {([
            ["terms", tr("I accept the terms and conditions.", "أوافق على الشروط والأحكام.")],
            ["correct", tr("I confirm that the information is correct.", "أؤكد أن المعلومات المدخلة صحيحة.")],
            ["privacy", tr("I consent to identity and compliance processing.", "أوافق على معالجة بيانات الهوية والامتثال.")],
          ] as const).map(([key, label]) => <label key={key} style={{ display: "flex", gap: 10, margin: "12px 0" }}><input type="checkbox" checked={consents[key]} onChange={(e) => setConsents({ ...consents, [key]: e.target.checked })} />{label}</label>)}
        </>}

        <div style={{ display: "flex", gap: 12, marginTop: 28 }}>
          <button disabled={step === 1 || saving} onClick={() => {
            if (step === 5 && !showSelfieInstructions) setShowSelfieInstructions(true);
            else { setShowSelfieInstructions(false); setStep(step - 1); }
          }} style={{ ...inputStyle, cursor: "pointer" }}>{tr("Back", "السابق")}</button>
          {step === 5 && showSelfieInstructions ? (
            <button type="button" onClick={() => setShowSelfieInstructions(false)} className="kyc-camera-button">
              {tr("Open camera", "تشغيل الكاميرا")} <ArrowRight size={18} />
            </button>
          ) : step < 6 ? <button disabled={saving} onClick={next} style={{ ...inputStyle, background: "#00C853", color: "#fff", border: 0, fontWeight: 700, cursor: "pointer" }}>{saving ? tr("Saving...", "جارٍ الحفظ...") : tr("Save & continue", "حفظ ومتابعة")}</button>
            : <button disabled={saving} onClick={submit} style={{ ...inputStyle, background: "#00C853", color: "#fff", border: 0, fontWeight: 700, cursor: "pointer" }}>{saving ? tr("Submitting...", "جارٍ الإرسال...") : tr("Submit for review", "إرسال للمراجعة")}</button>}
        </div>
      </section>
    </main>
  );
}
