"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import api from "@/lib/axios";
import AdminPageHeader from "@/components/admin/AdminPageHeader";
import { usePreferences } from "@/components/providers/AppPreferences";

type KYCRecordStatus = "pending" | "approved" | "flagged" | "rejected";

interface QueueItem {
  id: number;
  user_id: number;
  full_name: string;
  status: KYCRecordStatus;
  created_at: string;
  match_score: number | null;
  liveness_score: number | null;
  rejection_reason: string | null;
  reviewed_at: string | null;
  reviewed_by: number | null;
  selfie_presigned_url: string | null;
  id_photo_presigned_url: string | null;
  document_type: string | null;
}

const STATUS_BADGE_COLORS: Record<KYCRecordStatus, { bg: string; fg: string }> = {
  pending: { bg: "#FFFBEB", fg: "#B45309" },
  flagged: { bg: "#FFFBEB", fg: "#B45309" },
  approved: { bg: "#F0FDF4", fg: "#00A844" },
  rejected: { bg: "#FEF2F2", fg: "#DC2626" },
};

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "needs_review", label: "Needs review" },
  { value: "flagged", label: "Flagged" },
  { value: "rejected", label: "Rejected" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
];

const STAT_CARDS: { value: string; label: string; accent: string }[] = [
  { value: "needs_review", label: "Needs review", accent: "#0F172A" },
  { value: "flagged", label: "Flagged", accent: "#B45309" },
  { value: "pending", label: "Pending", accent: "#2563EB" },
  { value: "approved", label: "Approved", accent: "#00A844" },
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

function formatScore(score: number | null): string {
  if (score === null || score === undefined) return "—";
  return `${Math.round(score * 100)}%`;
}

function scoreTone(score: number | null): string {
  if (score === null || score === undefined) return "#9CA3AF";
  if (score >= 0.8) return "#00A844";
  if (score >= 0.5) return "#B45309";
  return "#DC2626";
}

export default function AdminKycQueuePage() {
  const { locale } = usePreferences();
  const tr = useCallback((en: string, ar: string) => locale === "ar" ? ar : en, [locale]);
  const statusLabel = (status: string) => locale === "ar" ? ({ needs_review: "تحتاج مراجعة", flagged: "معلّمة", rejected: "مرفوضة", pending: "قيد الانتظار", approved: "مقبولة" } as Record<string, string>)[status] ?? status : status.replaceAll("_", " ");
  const documentLabel = (type: string | null) => locale === "ar" ? ({ national_id: "هوية لبنانية", passport: "جواز سفر", drivers_license: "رخصة قيادة" } as Record<string, string>)[type ?? ""] ?? "—" : type?.replaceAll("_", " ") ?? "—";
  const [items, setItems] = useState<QueueItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("needs_review");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actingOnId, setActingOnId] = useState<number | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [counts, setCounts] = useState<Record<string, number | null>>({
    needs_review: null, flagged: null, pending: null, approved: null,
  });

  const fetchQueue = useCallback(async () => {
    try {
      const res = await api.get("/admin/kyc/queue", { params: { status: statusFilter } });
      setItems(res.data.items ?? []);
      setError("");
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setForbidden(true);
      else setError(tr("Failed to load KYC queue.", "تعذّر تحميل قائمة مراجعة الهوية."));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, tr]);

  const fetchCounts = useCallback(async () => {
    const entries = await Promise.all(
      STAT_CARDS.map(async ({ value }) => {
        try {
          const res = await api.get("/admin/kyc/queue", { params: { status: value, page_size: 1 } });
          return [value, res.data.total ?? 0] as const;
        } catch {
          return [value, null] as const;
        }
      })
    );
    setCounts(Object.fromEntries(entries));
  }, []);

  // fetchQueue's only setState calls are inside its try/catch/finally, all
  // of which run after `await api.get(...)` has already settled (success
  // or throw) -- no state update here is actually synchronous within this
  // effect's commit. This mirrors dashboard/page.tsx's fetchAll, which the
  // rule doesn't flag; its static analysis appears to key off the presence
  // of an explicit catch block rather than true reachability.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchQueue(); }, [fetchQueue]);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchCounts(); }, [fetchCounts]);

  const approve = async (id: number) => {
    setActingOnId(id);
    try {
      await api.patch(`/admin/kyc/${id}/approve`);
      setItems((prev) => prev.filter((i) => i.id !== id));
      fetchCounts();
    } catch { setError(tr("Approve failed.", "تعذّرت الموافقة على الطلب.")); }
    finally { setActingOnId(null); }
  };

  const reject = async (id: number) => {
    const reason = window.prompt(tr("Rejection reason:", "سبب الرفض:"));
    if (!reason) return;
    setActingOnId(id);
    try {
      await api.patch(`/admin/kyc/${id}/reject`, { rejection_reason: reason });
      setItems((prev) => prev.filter((i) => i.id !== id));
      fetchCounts();
    } catch { setError(tr("Reject failed.", "تعذّر رفض الطلب.")); }
    finally { setActingOnId(null); }
  };

  if (forbidden) {
    return (
      <div className="admin-page">
        <div className="admin-access-card">
          <strong>{tr("Compliance access required", "صلاحية الامتثال مطلوبة")}</strong>
          <p>{tr("Your account needs the compliance officer or administrator role to review KYC submissions.", "يجب أن يملك حسابك صلاحية مسؤول امتثال أو مدير لمراجعة طلبات التحقق من الهوية.")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <AdminPageHeader
        eyebrow={tr("Compliance operations", "عمليات الامتثال")}
        title={tr("KYC review queue", "قائمة مراجعة الهوية")}
        description={tr("Verify submitted identity documents, compare biometric checks, and resolve pending applications.", "راجع مستندات الهوية ونتائج المطابقة الحيوية واتخذ القرار المناسب للطلبات المعلّقة.")}
      />

      {/* Stat cards */}
      <div className="admin-summary-strip">
        {STAT_CARDS.map(({ value }) => (
          <button
            className={`admin-summary-item${statusFilter === value ? " is-primary" : ""}`}
            key={value}
            onClick={() => { setLoading(true); setStatusFilter(value); }}
          >
            <small>{statusLabel(value)}</small>
            <strong>
              {counts[value] === null ? <span style={{ display: "inline-block", width: "36px", height: "22px", borderRadius: "6px", backgroundColor: "#F3F4F6" }} /> : counts[value]}
            </strong>
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="admin-toolbar">
        <div className="admin-toolbar__filters">{STATUS_FILTERS.map((f) => (
          <button className={`admin-filter-button${statusFilter === f.value ? " is-active" : ""}`} key={f.value} onClick={() => { setLoading(true); setStatusFilter(f.value); }}>{statusLabel(f.value)}</button>
        ))}</div>
        <span className="admin-status admin-status--neutral">{tr("Identity review", "مراجعة الهوية")}</span>
      </div>

      {error && (
        <div className="admin-error-banner">
          {error}
        </div>
      )}

      {/* Queue table */}
      <div className="admin-data-card">
        <div className="admin-table-head admin-kyc-grid">
          {(locale === "ar" ? ["صاحب الطلب", "المستند", "تاريخ التقديم", "المطابقة", "التحقق الحيوي", "الحالة"] : ["Applicant", "Document", "Submitted", "Match", "Liveness", "Status"]).map((h) => (
            <p key={h} style={{ fontSize: "11px", fontWeight: "700", color: "#9CA3AF", textTransform: "uppercase", letterSpacing: "0.4px" }}>{h}</p>
          ))}
        </div>

        {loading ? (
          <div className="admin-empty"><div><p>{tr("Loading review queue...", "جارٍ تحميل قائمة المراجعة...")}</p></div></div>
        ) : items.length === 0 ? (
          <div className="admin-empty"><div><span className="admin-empty__icon"><CheckCircle2 size={24} /></span><strong>{tr("Queue is clear", "قائمة المراجعة فارغة")}</strong><p>{tr("No applications match this review status.", "لا توجد طلبات مطابقة لحالة المراجعة المحددة.")}</p></div></div>
        ) : (
          items.map((item) => (
            <div className="admin-kyc-record" key={item.id}>
              <div className="admin-table-row admin-kyc-grid">
                <div className="admin-person">
                  <div className="admin-person__avatar">
                    {initials(item.full_name)}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <p style={{ fontWeight: "700", color: "#0F172A", fontSize: "13px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.full_name}</p>
                    <p style={{ fontSize: "11px", color: "#9CA3AF" }}>{tr("User", "المستخدم")} #{item.user_id}</p>
                  </div>
                </div>
                <p style={{ fontSize: "12px", color: "#4B5563", textTransform: "capitalize" }}>{documentLabel(item.document_type)}</p>
                <p style={{ fontSize: "12px", color: "#4B5563" }}>{new Date(item.created_at).toLocaleDateString(locale === "ar" ? "ar-LB" : "en-GB")}</p>
                <p style={{ fontSize: "12px", fontWeight: "700", color: scoreTone(item.match_score) }}>{formatScore(item.match_score)}</p>
                <p style={{ fontSize: "12px", fontWeight: "700", color: scoreTone(item.liveness_score) }}>{formatScore(item.liveness_score)}</p>
                <span style={{ fontSize: "11px", fontWeight: "700", padding: "4px 10px", borderRadius: "999px", backgroundColor: STATUS_BADGE_COLORS[item.status].bg, color: STATUS_BADGE_COLORS[item.status].fg, width: "fit-content" }}>
                  {statusLabel(item.status)}
                </span>
              </div>

              <div style={{ padding: "0 20px 20px" }}>
                <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
                  <div style={{ display: "flex", gap: "12px" }}>
                    {item.selfie_presigned_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={item.selfie_presigned_url} alt={tr("Selfie", "الصورة الشخصية")} style={{ width: "110px", height: "140px", objectFit: "cover", borderRadius: "12px", border: "1px solid #E5E7EB" }} />
                    ) : (
                      <div style={{ width: "110px", height: "140px", borderRadius: "12px", border: "1px dashed #E5E7EB", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "11px", color: "#9CA3AF", textAlign: "center", padding: "8px" }}>{tr("No selfie", "لا توجد صورة شخصية")}</div>
                    )}
                    {item.id_photo_presigned_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={item.id_photo_presigned_url} alt={tr("ID document", "مستند الهوية")} style={{ width: "180px", height: "140px", objectFit: "cover", borderRadius: "12px", border: "1px solid #E5E7EB" }} />
                    ) : (
                      <div style={{ width: "180px", height: "140px", borderRadius: "12px", border: "1px dashed #E5E7EB", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "11px", color: "#9CA3AF" }}>{tr("No ID document", "لا يوجد مستند هوية")}</div>
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: "220px" }}>
                    <p style={{ fontSize: "12px", color: "#6B7280", lineHeight: 1.8 }}>
                      <strong style={{ color: "#0F172A" }}>{tr("Submitted", "تاريخ التقديم")}:</strong> {new Date(item.created_at).toLocaleString(locale === "ar" ? "ar-LB" : "en-GB")}<br />
                      {item.reviewed_at && <>
                        <strong style={{ color: "#0F172A" }}>{tr("Reviewed", "تاريخ المراجعة")}:</strong> {new Date(item.reviewed_at).toLocaleString(locale === "ar" ? "ar-LB" : "en-GB")}<br />
                      </>}
                      {item.rejection_reason && <>
                        <strong style={{ color: "#0F172A" }}>{tr("Reason", "السبب")}:</strong> {item.rejection_reason}
                      </>}
                    </p>
                    <div style={{ display: "flex", gap: "12px", marginTop: "16px" }}>
                      <button onClick={() => reject(item.id)} disabled={actingOnId === item.id}
                        className="admin-danger-button">
                        {tr("Reject", "رفض")}
                      </button>
                      <button onClick={() => approve(item.id)} disabled={actingOnId === item.id}
                        className="admin-primary-button">
                        {actingOnId === item.id ? tr("Working...", "جارٍ التنفيذ...") : tr("Approve", "موافقة")}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
