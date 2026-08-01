"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Building2,
  Check,
  Pencil,
  Plus,
  Search,
  Send,
  Smartphone,
  Trash2,
  Users,
  X,
} from "lucide-react";
import api from "@/lib/axios";
import { usePreferences } from "@/components/providers/AppPreferences";

type BeneficiaryType = "mobile" | "iban";

interface Beneficiary {
  id: number;
  nickname: string;
  type: BeneficiaryType;
  value: string;
}

function beneficiaryValuePlaceholder(type: BeneficiaryType) {
  return type === "mobile" ? "+96170123456" : "LB00...";
}

function getErrorMessage(error: unknown, fallback: string) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;

  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        typeof item?.msg === "string" ? item.msg : String(item)
      )
      .join(", ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }

  return fallback;
}

function PageHeader({ onBack }: { onBack: () => void }) {
  const { locale } = usePreferences();
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
      <button
        type="button"
        onClick={onBack}
        aria-label="Go back"
        style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <h1 style={{ fontSize: "18px", fontWeight: "700", color: "#000", margin: 0 }}>
        {locale === "ar" ? "المستفيدون المحفوظون" : "Saved Beneficiaries"}
      </h1>
    </div>
  );
}

export default function BeneficiariesPage() {
  const router = useRouter();
  const { locale } = usePreferences();
  const tr = (en: string, ar: string) => locale === "ar" ? ar : en;
  const [activeType, setActiveType] = useState<BeneficiaryType>("mobile");
  const [search, setSearch] = useState("");
  const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [nickname, setNickname] = useState("");
  const [value, setValue] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editNickname, setEditNickname] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    const params = new URLSearchParams({ type: activeType });
    const trimmedSearch = search.trim();

    if (trimmedSearch) {
      params.set("search", trimmedSearch);
    }

    api.get(`/beneficiaries?${params.toString()}`)
      .then((response) => {
        if (!cancelled) setBeneficiaries(response.data?.items ?? []);
      })
      .catch((requestError: unknown) => {
        if (!cancelled) {
          setBeneficiaries([]);
          setError(getErrorMessage(requestError, "Could not load beneficiaries."));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeType, search]);

  const refreshBeneficiaries = async () => {
    const params = new URLSearchParams({ type: activeType });
    const trimmedSearch = search.trim();

    if (trimmedSearch) {
      params.set("search", trimmedSearch);
    }

    const response = await api.get(`/beneficiaries?${params.toString()}`);
    setBeneficiaries(response.data?.items ?? []);
  };

  const handleAdd = async (event: React.FormEvent) => {
    event.preventDefault();
    setActionLoading("add");
    setError("");
    try {
      await api.post("/beneficiaries", {
        nickname: nickname.trim(),
        type: activeType,
        value: value.trim(),
      });
      await refreshBeneficiaries();
      setShowAddForm(false);
      setNickname("");
      setValue("");
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, "Could not add beneficiary."));
    } finally {
      setActionLoading(null);
    }
  };

  const handleRename = async (id: number) => {
    setActionLoading(`edit-${id}`);
    setError("");
    try {
      await api.patch(`/beneficiaries/${id}`, {
        nickname: editNickname.trim(),
      });
      await refreshBeneficiaries();
      setEditingId(null);
      setEditNickname("");
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, "Could not rename beneficiary."));
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (id: number) => {
    setActionLoading(`delete-${id}`);
    setError("");
    try {
      await api.delete(`/beneficiaries/${id}`);
      await refreshBeneficiaries();
      setConfirmDeleteId(null);
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, "Could not delete beneficiary."));
    } finally {
      setActionLoading(null);
    }
  };

  const switchType = (type: BeneficiaryType) => {
    if (type === activeType) return;
    setLoading(true);
    setError("");
    setActiveType(type);
    setSearch("");
    setShowAddForm(false);
    setNickname("");
    setValue("");
    setEditingId(null);
    setEditNickname("");
    setConfirmDeleteId(null);
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    border: "1.5px solid #E5E7EB",
    borderRadius: "12px",
    padding: "12px 14px",
    fontSize: "14px",
    color: "#000",
    outline: "none",
    boxSizing: "border-box",
  };

  return (
    <main className="bank-feature-page beneficiaries-page" style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px" }}>
      <PageHeader onBack={() => router.back()} />

      <section className="beneficiaries-hero">
        <div className="beneficiaries-hero__copy">
          <h2>{tr("Your beneficiaries", "المستفيدون")}</h2>
          <p>{tr("Manage saved mobile numbers and bank accounts.", "إدارة أرقام الهاتف والحسابات المصرفية المحفوظة.")}</p>
        </div>
        <div className="beneficiaries-hero__side">
          <button
            className="beneficiary-add-button"
            type="button"
            onClick={() => {
              setShowAddForm((current) => !current);
              setError("");
            }}
          >
            {showAddForm ? <X size={18} /> : <Plus size={18} />}
            {showAddForm ? tr("Close", "إغلاق") : tr("Add beneficiary", "إضافة مستفيد")}
          </button>
        </div>
      </section>

      <section className="beneficiary-toolbar">
        <div className="beneficiary-tabs" role="tablist" aria-label="Beneficiary type">
          {(["mobile", "iban"] as BeneficiaryType[]).map((type) => (
            <button
              type="button"
              role="tab"
              aria-selected={activeType === type}
              className={activeType === type ? "is-active" : ""}
              key={type}
              onClick={() => switchType(type)}
            >
              {type === "mobile" ? <Smartphone size={18} /> : <Building2 size={18} />}
              {type === "mobile" ? tr("Mobile", "رقم الهاتف") : tr("IBAN", "الآيبان")}
            </button>
          ))}
        </div>
        <label className="beneficiary-search">
          <Search size={19} />
          <input
            type="search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setLoading(true);
              setError("");
            }}
            placeholder={activeType === "mobile" ? tr("Search by nickname or mobile number", "البحث بالاسم أو رقم الهاتف") : tr("Search by nickname or IBAN", "البحث بالاسم أو رقم الآيبان")}
            aria-label="Search beneficiaries"
          />
        </label>
      </section>

      {showAddForm && (
        <form className="beneficiary-form" onSubmit={handleAdd}>
          <div className="beneficiary-form__heading">
            <span><Plus size={20} /></span>
            <div><h3>{tr("Add a new beneficiary", "إضافة مستفيد جديد")}</h3><p>{tr("Save their details for future transfers.", "احفظ بياناته لاستخدامها في التحويلات المقبلة.")}</p></div>
          </div>
          <div className="beneficiary-form__fields">
            <label><span>{tr("Display name", "اسم المستفيد")}</span><input value={nickname} onChange={(event) => setNickname(event.target.value)} placeholder={tr("e.g. Zahraa", "مثال: زهراء")} required style={inputStyle} /></label>
            <label>
              <span>{activeType === "mobile" ? tr("Mobile number", "رقم الهاتف") : tr("IBAN", "رقم الآيبان")}</span>
              <input
                className={error ? "has-error" : ""}
                value={value}
                onChange={(event) => { setValue(event.target.value); setError(""); }}
                placeholder={beneficiaryValuePlaceholder(activeType)}
                required
                aria-invalid={Boolean(error)}
                style={inputStyle}
              />
              {error && <small className="beneficiary-field-error">{error}</small>}
            </label>
          </div>
          <button className="beneficiary-form__submit" type="submit" disabled={actionLoading === "add" || !nickname.trim() || !value.trim()}>
            <Check size={18} /> {actionLoading === "add" ? tr("Adding...", "جارٍ الإضافة...") : tr("Save beneficiary", "حفظ المستفيد")}
          </button>
        </form>
      )}

      <div className="beneficiary-section-heading">
        <div>
          <h3>{activeType === "mobile" ? tr("Mobile beneficiaries", "مستفيدو الهاتف") : tr("IBAN beneficiaries", "مستفيدو الآيبان")}</h3>
          {search.trim() && <p>{tr(`Results for “${search.trim()}”`, `نتائج البحث عن «${search.trim()}»`)}</p>}
        </div>
        <span>{beneficiaries.length} {tr("saved", "محفوظ")}</span>
      </div>

      {loading ? (
        <div className="beneficiary-state"><span className="beneficiary-state__icon"><Users size={23} /></span><strong>{tr("Loading beneficiaries", "جارٍ تحميل المستفيدين")}</strong><p>{tr("Fetching your saved recipients...", "جارٍ تحميل المستفيدين المحفوظين...")}</p></div>
      ) : beneficiaries.length === 0 ? (
        <div className="beneficiary-state"><span className="beneficiary-state__icon"><Users size={23} /></span><strong>{tr("No beneficiaries found", "لا يوجد مستفيدون")}</strong><p>{search.trim() ? tr("Try another name or account detail.", "جرّب اسماً أو بيانات حساب أخرى.") : tr("Add your first trusted recipient to get started.", "أضف أول مستفيد موثوق للبدء.")}</p></div>
      ) : (
        <div className="beneficiary-grid">
          {beneficiaries.map((beneficiary) => (
            <article className="beneficiary-card" key={beneficiary.id}>
              <div className="beneficiary-card__top">
                <span className="beneficiary-avatar">{beneficiary.nickname.slice(0, 2).toUpperCase()}</span>
                <div className="beneficiary-card__identity">
                  <strong>{beneficiary.nickname}</strong>
                  <span>{beneficiary.value}</span>
                </div>
                <div className="beneficiary-card__actions">
                  <button type="button" className="is-transfer" title="Start transfer" aria-label={`Transfer to ${beneficiary.nickname}`} onClick={() => router.push("/transfer")}><Send size={18} /></button>
                  <button type="button" title="Rename" aria-label={`Rename ${beneficiary.nickname}`} onClick={() => { setEditingId(beneficiary.id); setEditNickname(beneficiary.nickname); setConfirmDeleteId(null); setError(""); }}><Pencil size={17} /></button>
                  <button type="button" className="is-danger" title="Delete" aria-label={`Delete ${beneficiary.nickname}`} onClick={() => { setConfirmDeleteId(beneficiary.id); setEditingId(null); setError(""); }}><Trash2 size={17} /></button>
                </div>
              </div>

              {editingId === beneficiary.id && (
                <div className="beneficiary-inline-panel">
                  <label><span>{tr("New display name", "الاسم الجديد")}</span><input value={editNickname} onChange={(event) => setEditNickname(event.target.value)} aria-label={`Rename ${beneficiary.nickname}`} style={inputStyle} /></label>
                  <div><button type="button" className="is-primary" onClick={() => handleRename(beneficiary.id)} disabled={actionLoading === `edit-${beneficiary.id}` || !editNickname.trim()}><Check size={16} /> {actionLoading === `edit-${beneficiary.id}` ? tr("Saving...", "جارٍ الحفظ...") : tr("Save", "حفظ")}</button><button type="button" onClick={() => { setEditingId(null); setEditNickname(""); }}><X size={16} /> {tr("Cancel", "إلغاء")}</button></div>
                </div>
              )}

              {confirmDeleteId === beneficiary.id && (
                <div className="beneficiary-delete-panel">
                  <div><strong>{tr("Remove this beneficiary?", "هل تريد حذف هذا المستفيد؟")}</strong><p>{tr("You can add them again later.", "يمكنك إضافته مجدداً لاحقاً.")}</p></div>
                  <div><button type="button" className="is-danger" onClick={() => handleDelete(beneficiary.id)} disabled={actionLoading === `delete-${beneficiary.id}`}><Trash2 size={16} /> {actionLoading === `delete-${beneficiary.id}` ? tr("Deleting...", "جارٍ الحذف...") : tr("Remove", "حذف")}</button><button type="button" onClick={() => setConfirmDeleteId(null)}>{tr("Cancel", "إلغاء")}</button></div>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
