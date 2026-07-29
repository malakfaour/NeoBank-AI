"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";
import SelfieCapture from "@/components/kyc/SelfieCapture";

type Profile = Record<string, string>;
type Workflow = "not_started" | "in_progress" | "pending" | "approved" | "rejected";
export type KYCDocumentType = "national_id" | "passport";

export function buildKycUploadForm(
  files: { front: File; back: File },
  documentType: KYCDocumentType,
) {
  const form = new FormData();
  form.append("id_photo", files.front);
  form.append("back_id_photo", files.back);
  form.append("document_type", documentType);
  form.append("submit_for_review", "false");
  return form;
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
      { key: "identification_type", label: "Identification type", options: ["national_id", "passport"], required: true },
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
  if (!identificationComplete || !data.has_front_id || !data.has_back_id) return 6;
  return Math.min(Math.max(data.current_step || 6, 1), 6);
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "12px 14px", borderRadius: "12px",
  border: "1px solid #E5E7EB", background: "#fff", color: "#111",
};

const multipartRequestConfig = {
  headers: { "Content-Type": "multipart/form-data" },
};

export default function KYCPage() {
  const router = useRouter();
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

  useEffect(() => {
    api.get<KYCResponse>("/kyc/profile").then(({ data }) => {
      setProfile(data.profile_data ?? {});
      setStep(getKycResumeStep(data));
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
      if (field.required && !String(profile[field.key] ?? "").trim()) nextErrors[field.key] = `${field.label} is required.`;
    });
    if (step === 3 && profile.occupation === "employee") {
      visibleFields
        .filter((field) => ["employer_name", "position", "employment_address", "employer_phone"].includes(field.key))
        .forEach((field) => {
          if (!String(profile[field.key] ?? "").trim()) nextErrors[field.key] = `${field.label} is required.`;
        });
    }
    if (step === 5) {
      if (!documents.selfie && !files.selfie) nextErrors.selfie = "Selfie is required.";
    }
    if (step === 6) {
      if (!documents.front && !files.front) nextErrors.front = "Front ID image is required.";
      if (!documents.back && !files.back) nextErrors.back = "Back ID image is required.";
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
    if (step === 6 && files.front && files.back) {
      const form = buildKycUploadForm(
        { front: files.front, back: files.back },
        (profile.identification_type as KYCDocumentType) || "national_id",
      );
      await api.post("/kyc/upload", form, multipartRequestConfig);
      setDocuments((current) => ({ ...current, front: true, back: true }));
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
    } catch {
      setMessage("We could not save your progress. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const submit = async () => {
    if (!validateStep()) return;
    if (!consents.terms || !consents.correct || !consents.privacy) {
      setMessage("Accept all confirmations before submitting.");
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
      setMessage(fields?.length ? `Missing: ${fields.join(", ")}` : "Submission failed. Review the form and try again.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <main style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>Loading profile…</main>;
  if (workflow === "approved" || workflow === "pending") return (
    <main style={{ minHeight: "100vh", background: "#F5F5F5", display: "grid", placeItems: "center", padding: 20 }}>
      <section style={{ maxWidth: 520, background: "#fff", padding: 32, borderRadius: 24, textAlign: "center" }}>
        <div style={{ fontSize: 44 }}>{workflow === "approved" ? "✅" : "⏳"}</div>
        <h1>{workflow === "approved" ? "Identity verified" : "We're reviewing your documents"}</h1>
        <p style={{ color: "#666" }}>{workflow === "approved" ? "Your full NeoBank access is unlocked." : "Your selfie and ID have been submitted for manual review. This usually takes 2–4 business days. Transfers, Currency Exchange, and Top Ups will be available after approval."}</p>
        <button onClick={() => router.push("/dashboard")} style={{ ...inputStyle, marginTop: 20, background: "#00C853", color: "#fff", border: 0, fontWeight: 700 }}>Back to dashboard</button>
      </section>
    </main>
  );

  return (
    <main style={{ minHeight: "100vh", background: "#F5F5F5", padding: "24px 16px" }}>
      <section style={{ maxWidth: 760, margin: "0 auto", background: "#fff", padding: 28, borderRadius: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 24 }}>
          {steps.map((_, index) => <div key={index} style={{ height: 6, flex: 1, borderRadius: 99, background: index < step ? "#00C853" : "#E5E7EB" }} />)}
        </div>
        {workflow === "rejected" && <div role="alert" style={{ background: "#FEF2F2", color: "#991B1B", padding: 14, borderRadius: 12, marginBottom: 18 }}>Your verification needs attention. {rejectionReason || "Review and update the requested information."}</div>}
        <p style={{ color: "#00A844", fontWeight: 700, fontSize: 13 }}>STEP {step} OF 6</p>
        <h1 style={{ margin: "4px 0" }}>{steps[step - 1].title}</h1>
        <p style={{ color: "#777", marginBottom: 24 }}>{steps[step - 1].subtitle}</p>
        {message && <div role="alert" style={{ color: "#B91C1C", background: "#FEF2F2", padding: 12, borderRadius: 10, marginBottom: 16 }}>{message}</div>}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 16 }}>
          {visibleFields.map((field) => <label key={field.key} style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 600 }}>
            {field.label}{field.required ? " *" : ""}
            {field.options ? <select value={profile[field.key] ?? ""} onChange={(e) => setProfile({ ...profile, [field.key]: e.target.value })} style={inputStyle}>
              <option value="">Select</option>{field.options.map((option) => <option key={option} value={option}>{option.replaceAll("_", " ")}</option>)}
            </select> : <input type={field.type || "text"} value={profile[field.key] ?? ""} onChange={(e) => setProfile({ ...profile, [field.key]: e.target.value })} style={inputStyle} />}
            {errors[field.key] && <span style={{ color: "#B91C1C", fontWeight: 400 }}>{errors[field.key]}</span>}
          </label>)}
          {step === 6 && (["front", "back"] as const).map((key) => <label key={key} style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 600 }}>
            {key === "front" ? "Front ID image" : "Back ID image"} *
            <input type="file" accept="image/jpeg,image/png" onChange={(e) => setFiles({ ...files, [key]: e.target.files?.[0] })} style={inputStyle} />
            {documents[key] && !files[key] && <span style={{ color: "#00A844" }}>Already uploaded</span>}
            {errors[key] && <span style={{ color: "#B91C1C", fontWeight: 400 }}>{errors[key]}</span>}
          </label>)}
          {step === 5 && <div style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 600, gridColumn: "1 / -1" }}>
            Selfie *
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
          </div>}
        </div>

        {step === 6 && <>
          <div style={{ display: "grid", gap: 12, marginBottom: 20 }}>
            {[...steps.slice(0, 4), steps[5]].map((section) => <details key={section.title} style={{ border: "1px solid #E5E7EB", borderRadius: 12, padding: 14 }}>
              <summary style={{ fontWeight: 700, cursor: "pointer" }}>{section.title}</summary>
              {section.fields.filter((field) => profile[field.key]).map((field) => <p key={field.key} style={{ color: "#666", fontSize: 13 }}><strong>{field.label}:</strong> {field.key === "identification_number" ? `••••${profile[field.key].slice(-4)}` : profile[field.key]}</p>)}
            </details>)}
          </div>
          {([
            ["terms", "I accept the terms and conditions."],
            ["correct", "I confirm that the information is correct."],
            ["privacy", "I consent to identity and compliance processing."],
          ] as const).map(([key, label]) => <label key={key} style={{ display: "flex", gap: 10, margin: "12px 0" }}><input type="checkbox" checked={consents[key]} onChange={(e) => setConsents({ ...consents, [key]: e.target.checked })} />{label}</label>)}
        </>}

        <div style={{ display: "flex", gap: 12, marginTop: 28 }}>
          <button disabled={step === 1 || saving} onClick={() => setStep(step - 1)} style={{ ...inputStyle, cursor: "pointer" }}>Back</button>
          {step < 6 ? <button disabled={saving} onClick={next} style={{ ...inputStyle, background: "#00C853", color: "#fff", border: 0, fontWeight: 700, cursor: "pointer" }}>{saving ? "Saving…" : "Save & continue"}</button>
            : <button disabled={saving} onClick={submit} style={{ ...inputStyle, background: "#00C853", color: "#fff", border: 0, fontWeight: 700, cursor: "pointer" }}>{saving ? "Submitting…" : "Submit for review"}</button>}
        </div>
      </section>
    </main>
  );
}
