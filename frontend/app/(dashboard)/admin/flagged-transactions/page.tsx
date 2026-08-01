"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";
import api from "@/lib/axios";
import AdminPageHeader from "@/components/admin/AdminPageHeader";
import { usePreferences } from "@/components/providers/AppPreferences";

interface FlaggedTransactionItem {
  id: number;
  sender_id: number;
  sender_name: string;
  sender_email: string;
  amount: string;
  currency: string;
  fraud_score: number | null;
  scoring_model: string | null;
  status: string;
  created_at: string;
}

export default function AdminFlaggedTransactionsPage() {
  const { locale } = usePreferences();
  const tr = useCallback((en: string, ar: string) => locale === "ar" ? ar : en, [locale]);
  const statusLabel = (status: string) => locale === "ar" ? ({ pending: "قيد الانتظار", completed: "مكتملة", flagged: "معلّمة", failed: "فشلت", reversed: "معكوسة" } as Record<string, string>)[status] ?? status : status.replaceAll("_", " ");
  const [items, setItems] = useState<FlaggedTransactionItem[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actingOnId, setActingOnId] = useState<number | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const fetchQueue = useCallback(async () => {
    try {
      const res = await api.get("/admin/flagged-transactions", { params: { page, page_size: 20 } });
      setItems(res.data.items ?? []);
      setTotalPages(res.data.total_pages ?? 1);
      setError("");
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setForbidden(true);
      else setError(tr("Failed to load the flagged transactions queue.", "تعذّر تحميل قائمة المعاملات المعلّمة."));
    } finally {
      setLoading(false);
    }
  }, [page, tr]);

  // Same pattern as admin/kyc/page.tsx's fetchQueue -- see that file's
  // comment for why this suppression is needed.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  const resolve = async (id: number, resolution: "legitimate" | "confirmed_fraud") => {
    if (resolution === "confirmed_fraud") {
      const confirmed = window.confirm(
        tr("This will reverse the transaction and credit the sender's wallet back. This cannot be undone. Continue?", "سيتم عكس المعاملة وإعادة المبلغ إلى محفظة المرسل. لا يمكن التراجع عن هذا الإجراء. هل تريد المتابعة؟")
      );
      if (!confirmed) return;
    }
    setActingOnId(id);
    try {
      await api.post(`/admin/transactions/${id}/resolve-flag`, { resolution });
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? tr("Resolving this flag failed.", "تعذّر إغلاق هذه المراجعة."));
    } finally {
      setActingOnId(null);
    }
  };

  if (forbidden) {
    return (
      <div className="admin-page">
        <div className="admin-access-card">
          <strong>{tr("Compliance access required", "صلاحية الامتثال مطلوبة")}</strong>
          <p>{tr("Your account needs the compliance officer or administrator role to review flagged transactions.", "يجب أن يملك حسابك صلاحية مسؤول امتثال أو مدير لمراجعة المعاملات المعلّمة.")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <AdminPageHeader
        eyebrow={tr("Risk operations", "عمليات المخاطر")}
        title={tr("Flagged transactions", "المعاملات المعلّمة")}
        description={tr("Investigate unusual activity, validate legitimate payments, and resolve confirmed fraud.", "راجع النشاط غير المعتاد، وأكد المعاملات السليمة، واتخذ القرار المناسب بشأن حالات الاحتيال.")}
      />

      <div className="admin-toolbar">
        <div className="admin-toolbar__filters">
          <button className="admin-filter-button is-active" type="button"><ShieldAlert size={15} /> {tr("Review queue", "قائمة المراجعة")}</button>
        </div>
        <span className="admin-status admin-status--warning">{locale === "ar" ? `${items.length} بانتظار المراجعة` : `${items.length} awaiting review`}</span>
      </div>

      {error && (
        <div className="admin-error-banner">
          {error}
        </div>
      )}

      <section className="admin-data-card">
        <div className="admin-table-head admin-risk-grid">
          <span>{tr("Account", "الحساب")}</span><span>{tr("Amount", "المبلغ")}</span><span>{tr("Risk signal", "مؤشر المخاطر")}</span><span>{tr("Flagged", "تاريخ الرصد")}</span><span>{tr("Decision", "القرار")}</span>
        </div>
        {loading ? (
          <div className="admin-empty"><div><p>{tr("Loading risk queue...", "جارٍ تحميل قائمة المخاطر...")}</p></div></div>
        ) : items.length === 0 ? (
          <div className="admin-empty"><div><span className="admin-empty__icon"><CheckCircle2 size={24} /></span><strong>{tr("Risk queue is clear", "قائمة المخاطر فارغة")}</strong><p>{tr("There are no flagged transactions waiting for review.", "لا توجد معاملات معلّمة بانتظار المراجعة.")}</p></div></div>
        ) : items.map((item) => (
          <div className="admin-table-row admin-risk-grid" key={item.id}>
            <div className="admin-person">
              <span className="admin-person__avatar">{item.sender_name.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase()}</span>
              <span><strong>{item.sender_name}</strong><small>{item.sender_email} · {tr("TX", "معاملة")} #{item.id}</small></span>
            </div>
            <div className="admin-cell"><span className="admin-cell-label">{tr("Amount", "المبلغ")}</span><strong>{Number(item.amount).toLocaleString(locale === "ar" ? "ar-LB" : "en-US")} {item.currency}</strong><small>{statusLabel(item.status)}</small></div>
            <div className="admin-cell"><span className="admin-cell-label">{tr("Risk signal", "مؤشر المخاطر")}</span><span className="admin-status admin-status--warning"><AlertTriangle size={11} />{item.fraud_score !== null ? item.fraud_score.toFixed(4) : "—"}</span><small>{item.scoring_model ?? tr("Unknown model", "نموذج غير معروف")}</small></div>
            <div className="admin-cell"><span className="admin-cell-label">{tr("Flagged", "تاريخ الرصد")}</span><strong>{new Date(item.created_at).toLocaleDateString(locale === "ar" ? "ar-LB" : "en-GB")}</strong><small>{new Date(item.created_at).toLocaleTimeString(locale === "ar" ? "ar-LB" : "en-GB", { hour: "2-digit", minute: "2-digit" })}</small></div>
            <div className="admin-row-actions">
              <button className="admin-secondary-button" onClick={() => resolve(item.id, "legitimate")} disabled={actingOnId === item.id}>{tr("Legitimate", "معاملة سليمة")}</button>
              <button className="admin-danger-button" onClick={() => resolve(item.id, "confirmed_fraud")} disabled={actingOnId === item.id}>{actingOnId === item.id ? tr("Working...", "جارٍ التنفيذ...") : tr("Confirm fraud", "تأكيد الاحتيال")}</button>
            </div>
          </div>
        ))}
        {totalPages > 1 && <div className="admin-pagination">
          <button className="admin-secondary-button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>{tr("Previous", "السابق")}</button>
          <span>{locale === "ar" ? `الصفحة ${page} من ${totalPages}` : `Page ${page} of ${totalPages}`}</span>
          <button className="admin-secondary-button" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>{tr("Next", "التالي")}</button>
        </div>}
      </section>
    </div>
  );
}
