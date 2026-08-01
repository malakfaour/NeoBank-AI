"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Search, WalletCards } from "lucide-react";
import api from "@/lib/axios";
import AdminPageHeader from "@/components/admin/AdminPageHeader";
import { usePreferences } from "@/components/providers/AppPreferences";

interface AdminTransactionItem {
  id: number;
  sender_id: number;
  sender_name: string;
  receiver_id: number;
  receiver_name: string;
  amount: string;
  currency: string;
  category: string | null;
  status: string;
  created_at: string;
}

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "completed", label: "Completed" },
  { value: "flagged", label: "Flagged" },
  { value: "failed", label: "Failed" },
  { value: "reversed", label: "Reversed" },
];

export default function AdminTransactionsPage() {
  const { locale } = usePreferences();
  const tr = useCallback((en: string, ar: string) => locale === "ar" ? ar : en, [locale]);
  const statusLabel = (status: string) => locale === "ar" ? ({ "": "الكل", pending: "قيد الانتظار", completed: "مكتملة", flagged: "معلّمة", failed: "فشلت", reversed: "معكوسة" } as Record<string, string>)[status] ?? status : status.replaceAll("_", " ") || "All";
  const categoryLabel = (category: string | null) => locale === "ar" ? ({ transfer: "تحويل", exchange: "صرف عملات", bills: "فواتير", topup: "إضافة رصيد", other: "أخرى" } as Record<string, string>)[category?.toLowerCase() ?? ""] ?? "غير مصنّفة" : category ?? "Uncategorized";
  const [items, setItems] = useState<AdminTransactionItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [forbidden, setForbidden] = useState(false);

  const fetchTransactions = useCallback(async () => {
    try {
      const res = await api.get("/admin/transactions", {
        params: {
          page,
          page_size: 20,
          status: statusFilter || undefined,
          q: query || undefined,
        },
      });
      setItems(res.data.items ?? []);
      setTotalPages(res.data.total_pages ?? 1);
      setError("");
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setForbidden(true);
      else setError(tr("Failed to load transactions.", "تعذّر تحميل المعاملات."));
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, query, tr]);

  // Same pattern as admin/kyc/page.tsx's fetchQueue -- see that file's
  // comment for why this suppression is needed.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchTransactions(); }, [fetchTransactions]);

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setLoading(true);
    setQuery(searchInput);
  };

  if (forbidden) {
    return (
      <div className="admin-page">
        <div className="admin-access-card">
          <strong>{tr("Compliance access required", "صلاحية الامتثال مطلوبة")}</strong>
          <p>{tr("Your account needs the compliance officer or administrator role to view all transactions.", "يجب أن يملك حسابك صلاحية مسؤول امتثال أو مدير لعرض جميع المعاملات.")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <AdminPageHeader
        eyebrow={tr("Ledger operations", "عمليات السجل المالي")}
        title={tr("All transactions", "جميع المعاملات")}
        description={tr("Search the complete Neo ledger and monitor payment status across every customer account.", "ابحث في سجل Neo المالي الكامل وتابع حالة المدفوعات عبر جميع حسابات العملاء.")}
      />

      <div className="admin-toolbar">
        <div className="admin-toolbar__filters">
          {STATUS_FILTERS.map((f) => <button className={`admin-filter-button${statusFilter === f.value ? " is-active" : ""}`} key={f.value} onClick={() => { setLoading(true); setPage(1); setStatusFilter(f.value); }}>{statusLabel(f.value)}</button>)}
        </div>
        <form className="admin-search" onSubmit={submitSearch}>
          <Search size={17} />
          <input value={searchInput} onChange={(e) => setSearchInput(e.target.value)} placeholder={tr("Search name or email", "ابحث بالاسم أو البريد الإلكتروني")} />
          <button className="admin-primary-button" type="submit">{tr("Search", "بحث")}</button>
        </form>
      </div>

      {error && (
        <div className="admin-error-banner">
          {error}
        </div>
      )}

      <section className="admin-data-card">
        <div className="admin-table-head admin-transactions-grid"><span>{tr("Route", "مسار التحويل")}</span><span>{tr("Category", "الفئة")}</span><span>{tr("Amount", "المبلغ")}</span><span>{tr("Created", "التاريخ")}</span><span>{tr("Status", "الحالة")}</span></div>
        {loading ? <div className="admin-empty"><div><p>{tr("Loading transactions...", "جارٍ تحميل المعاملات...")}</p></div></div>
        : items.length === 0 ? <div className="admin-empty"><div><span className="admin-empty__icon"><WalletCards size={24} /></span><strong>{tr("No transactions found", "لا توجد معاملات")}</strong><p>{tr("Try changing your search or status filter.", "جرّب تغيير عبارة البحث أو فلتر الحالة.")}</p></div></div>
        : items.map((item) => <div className="admin-table-row admin-transactions-grid" key={item.id}>
          <div className="admin-person admin-transaction-route">
            <span className="admin-person__avatar"><ArrowRight size={17} /></span>
            <span><strong>{item.sender_name} → {item.receiver_name}</strong><small>{tr("Transaction", "معاملة")} #{item.id}</small></span>
          </div>
          <div className="admin-cell"><span className="admin-cell-label">{tr("Category", "الفئة")}</span><strong>{categoryLabel(item.category)}</strong></div>
          <div className="admin-cell"><span className="admin-cell-label">{tr("Amount", "المبلغ")}</span><strong>{Number(item.amount).toLocaleString(locale === "ar" ? "ar-LB" : "en-US")} {item.currency}</strong></div>
          <div className="admin-cell"><span className="admin-cell-label">{tr("Created", "التاريخ")}</span><strong>{new Date(item.created_at).toLocaleDateString(locale === "ar" ? "ar-LB" : "en-GB")}</strong><small>{new Date(item.created_at).toLocaleTimeString(locale === "ar" ? "ar-LB" : "en-GB", { hour: "2-digit", minute: "2-digit" })}</small></div>
          <div className="admin-cell"><span className="admin-cell-label">{tr("Status", "الحالة")}</span><span className={`admin-status ${item.status === "completed" ? "admin-status--success" : item.status === "failed" ? "admin-status--danger" : item.status === "pending" || item.status === "flagged" ? "admin-status--warning" : "admin-status--neutral"}`}>{statusLabel(item.status)}</span></div>
        </div>)}
        {totalPages > 1 && <div className="admin-pagination">
          <button className="admin-secondary-button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>{tr("Previous", "السابق")}</button>
          <span>{locale === "ar" ? `الصفحة ${page} من ${totalPages}` : `Page ${page} of ${totalPages}`}</span>
          <button className="admin-secondary-button" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>{tr("Next", "التالي")}</button>
        </div>}
      </section>
    </div>
  );
}
