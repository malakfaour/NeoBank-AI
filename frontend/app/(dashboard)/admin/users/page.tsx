"use client";

import { useState } from "react";
import { Search, UsersRound } from "lucide-react";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";
import AdminPageHeader from "@/components/admin/AdminPageHeader";
import { usePreferences } from "@/components/providers/AppPreferences";

interface UserSearchItem {
  id: number;
  full_name: string;
  email: string;
  phone: string;
  kyc_status: string;
  role: string;
  is_active: boolean;
}

interface WalletItem {
  id: number;
  currency: string;
  balance: string;
  account_number: string | null;
  iban: string | null;
}

const KYC_BADGE_COLORS: Record<string, { bg: string; fg: string }> = {
  pending: { bg: "#FFFBEB", fg: "#B45309" },
  flagged: { bg: "#FFFBEB", fg: "#B45309" },
  approved: { bg: "#F0FDF4", fg: "#00A844" },
  rejected: { bg: "#FEF2F2", fg: "#DC2626" },
  not_submitted: { bg: "#F3F4F6", fg: "#4B5563" },
};

const ROLE_BADGE_COLORS: Record<string, { bg: string; fg: string }> = {
  admin: { bg: "#10251B", fg: "#78EDB3" },
  compliance_officer: { bg: "#E8F8EF", fg: "#007D44" },
  customer: { bg: "#EEF2EF", fg: "#536159" },
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export default function AdminUsersPage() {
  const { locale } = usePreferences();
  const tr = (en: string, ar: string) => locale === "ar" ? ar : en;
  const roleLabel = (value: string) => locale === "ar" ? ({ admin: "مدير النظام", compliance_officer: "مسؤول امتثال", customer: "عميل" } as Record<string, string>)[value] ?? value : value.replaceAll("_", " ");
  const kycLabel = (value: string) => locale === "ar" ? ({ pending: "قيد الانتظار", flagged: "معلّم", approved: "مكتمل", rejected: "مرفوض", not_submitted: "غير مقدّم" } as Record<string, string>)[value] ?? value : value.replaceAll("_", " ");
  const role = useAuthStore((s) => s.user?.role);
  const canAdjust = role === "admin";

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserSearchItem[]>([]);
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [forbidden, setForbidden] = useState(false);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [wallets, setWallets] = useState<WalletItem[]>([]);
  const [loadingWallets, setLoadingWallets] = useState(false);
  const [adjustingId, setAdjustingId] = useState<number | null>(null);
  const [statusUpdatingId, setStatusUpdatingId] = useState<number | null>(null);

  const search = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setSearched(true);
    setError("");
    setExpandedId(null);
    try {
      const res = await api.get("/admin/users/search", { params: { q: query, page: 1, page_size: 20 } });
      setResults(res.data.items ?? []);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setForbidden(true);
      else setError(tr("Search failed.", "تعذّر البحث عن الحسابات."));
    } finally {
      setSearching(false);
    }
  };

  const toggleRow = async (user: UserSearchItem) => {
    if (expandedId === user.id) { setExpandedId(null); return; }
    setExpandedId(user.id);
    setWallets([]);
    setLoadingWallets(true);
    setError("");
    try {
      const res = await api.get(`/admin/users/${user.id}/wallets`);
      setWallets(res.data.items ?? []);
    } catch {
      setError(tr("Failed to load wallets.", "تعذّر تحميل المحافظ."));
    } finally {
      setLoadingWallets(false);
    }
  };

  const adjustWallet = async (wallet: WalletItem) => {
    const direction = window.prompt(tr("Direction? Type \"credit\" or \"debit\"", "نوع العملية؟ اكتب credit للإضافة أو debit للخصم"));
    if (direction !== "credit" && direction !== "debit") return;
    const amountStr = window.prompt(tr(`Amount (${wallet.currency}):`, `المبلغ (${wallet.currency}):`));
    if (!amountStr) return;
    const amount = Number(amountStr);
    if (!amount || amount <= 0) { setError(tr("Invalid amount.", "المبلغ غير صالح.")); return; }
    const reason = window.prompt(tr("Reason for adjustment:", "سبب تعديل الرصيد:"));
    if (!reason) return;

    setAdjustingId(wallet.id);
    setError("");
    try {
      const res = await api.post(`/admin/wallets/${wallet.id}/adjust`, {
        direction,
        amount,
        reason,
      });
      setWallets((prev) =>
        prev.map((w) => (w.id === wallet.id ? { ...w, balance: res.data.new_balance } : w))
      );
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : tr("Adjustment failed.", "تعذّر تعديل الرصيد."));
    } finally {
      setAdjustingId(null);
    }
  };

  const toggleUserStatus = async (user: UserSearchItem) => {
    const suspending = user.is_active;
    if (!window.confirm(suspending
      ? tr(`Suspend ${user.full_name}? They won't be able to log in until reactivated.`, `هل تريد إيقاف حساب ${user.full_name}؟ لن يتمكن من تسجيل الدخول حتى إعادة تفعيله.`)
      : tr(`Reactivate ${user.full_name}?`, `هل تريد إعادة تفعيل حساب ${user.full_name}؟`))) {
      return;
    }
    setStatusUpdatingId(user.id);
    setError("");
    try {
      const res = await api.post(`/admin/users/${user.id}/${suspending ? "suspend" : "activate"}`);
      setResults((prev) => prev.map((u) => (u.id === user.id ? { ...u, is_active: res.data.is_active } : u)));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : tr("Could not update account status.", "تعذّر تحديث حالة الحساب."));
    } finally {
      setStatusUpdatingId(null);
    }
  };

  if (forbidden) {
    return (
      <div className="admin-page">
        <div className="admin-access-card">
          <strong>{tr("Compliance access required", "صلاحية الامتثال مطلوبة")}</strong>
          <p>{tr("Your account needs the compliance officer or administrator role to look up users.", "يجب أن يملك حسابك صلاحية مسؤول امتثال أو مدير للبحث عن المستخدمين.")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <AdminPageHeader
        eyebrow={tr("Customer operations", "عمليات العملاء")}
        title={tr("User accounts", "حسابات المستخدمين")}
        description={tr("Find customers, inspect their wallets, and manage account access from one secure workspace.", "ابحث عن العملاء وراجع محافظهم وأدر صلاحية الوصول إلى حساباتهم من مساحة آمنة واحدة.")}
      />

      {/* Search */}
      <div className="admin-toolbar admin-user-toolbar">
        <div><strong>{tr("Account directory", "دليل الحسابات")}</strong><small>{tr("Search using customer or account details.", "ابحث باستخدام بيانات العميل أو الحساب.")}</small></div>
        <form className="admin-search" onSubmit={search}>
          <Search size={17} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={tr("Name, phone, or account number", "الاسم أو الهاتف أو رقم الحساب")} />
          <button className="admin-primary-button" type="submit" disabled={searching}>{searching ? tr("Searching...", "جارٍ البحث...") : tr("Search", "بحث")}</button>
        </form>
      </div>

      {error && (
        <div className="admin-error-banner">
          {error}
        </div>
      )}

      {!searched && (
        <div className="admin-data-card">
          <div className="admin-empty"><div><span className="admin-empty__icon"><UsersRound size={24} /></span><strong>{tr("Search the account directory", "ابحث في دليل الحسابات")}</strong><p>{tr("Enter a customer name, phone number, or account number to begin.", "أدخل اسم العميل أو رقم الهاتف أو رقم الحساب للبدء.")}</p></div></div>
        </div>
      )}

      {/* Results table */}
      {searched && (
        <div className="admin-data-card">
          <div className="admin-table-head admin-users-grid">
            {(locale === "ar" ? ["الحساب", "الصلاحية", "التحقق من الهوية", "الحالة", ""] : ["Account", "Role", "KYC", "Status", ""]).map((h) => (
              <p key={h} style={{ fontSize: "11px", fontWeight: "700", color: "#9CA3AF", textTransform: "uppercase", letterSpacing: "0.4px" }}>{h}</p>
            ))}
          </div>

          {results.length === 0 ? (
            <div className="admin-empty"><div><span className="admin-empty__icon"><UsersRound size={24} /></span><strong>{tr("No matching accounts", "لا توجد حسابات مطابقة")}</strong><p>{tr(`No accounts match “${query}”.`, `لا توجد حسابات تطابق «${query}».`)}</p></div></div>
          ) : (
            results.map((u) => {
              const isExpanded = expandedId === u.id;
              const roleColors = ROLE_BADGE_COLORS[u.role] ?? ROLE_BADGE_COLORS.customer;
              const kycColors = KYC_BADGE_COLORS[u.kyc_status] ?? KYC_BADGE_COLORS.not_submitted;
              return (
                <div className="admin-user-record" key={u.id}>
                  <div
                    className="admin-table-row admin-users-grid"
                    onClick={() => toggleRow(u)}
                    style={{ cursor: "pointer" }}
                  >
                    <div className="admin-person">
                      <div className="admin-person__avatar">
                        {initials(u.full_name)}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <p style={{ fontWeight: "700", color: "#0F172A", fontSize: "13px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{u.full_name}</p>
                        <p style={{ fontSize: "11px", color: "#9CA3AF", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{u.email} &middot; {u.phone}</p>
                      </div>
                    </div>
                    <span style={{ fontSize: "11px", fontWeight: "700", padding: "4px 10px", borderRadius: "999px", backgroundColor: roleColors.bg, color: roleColors.fg, width: "fit-content", textTransform: "capitalize" }}>
                      {roleLabel(u.role)}
                    </span>
                    <span style={{ fontSize: "11px", fontWeight: "700", padding: "4px 10px", borderRadius: "999px", backgroundColor: kycColors.bg, color: kycColors.fg, width: "fit-content", textTransform: "capitalize" }}>
                      {kycLabel(u.kyc_status)}
                    </span>
                    <span style={{ fontSize: "11px", fontWeight: "700", padding: "4px 10px", borderRadius: "999px", backgroundColor: u.is_active ? "#F0FDF4" : "#FEF2F2", color: u.is_active ? "#00A844" : "#DC2626", width: "fit-content" }}>
                      {u.is_active ? tr("Active", "نشط") : tr("Suspended", "موقوف")}
                    </span>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "10px" }}>
                      {canAdjust && (
                        <button
                          onClick={(e) => { e.stopPropagation(); toggleUserStatus(u); }}
                          disabled={statusUpdatingId === u.id}
                          style={{
                            padding: "7px 12px",
                            borderRadius: "10px",
                            border: `1.5px solid ${u.is_active ? "#FECACA" : "#00A844"}`,
                            backgroundColor: "#fff",
                            color: u.is_active ? "#DC2626" : "#00A844",
                            fontSize: "11px",
                            fontWeight: "700",
                            cursor: statusUpdatingId === u.id ? "not-allowed" : "pointer",
                          }}
                        >
                          {statusUpdatingId === u.id ? tr("Working...", "جارٍ التنفيذ...") : u.is_active ? tr("Suspend", "إيقاف") : tr("Reactivate", "إعادة التفعيل")}
                        </button>
                      )}
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" style={{ transform: isExpanded ? "rotate(180deg)" : "none", transition: "transform 0.15s", flexShrink: 0 }}>
                        <path d="M6 9l6 6 6-6" stroke="#9CA3AF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </div>
                  </div>

                  {isExpanded && (
                    <div style={{ padding: "0 20px 20px", backgroundColor: "#FAFBFC" }}>
                      <p style={{ fontSize: "11px", fontWeight: "700", color: "#9CA3AF", textTransform: "uppercase", letterSpacing: "0.4px", marginBottom: "10px", paddingTop: "4px" }}>{tr("Wallets", "المحافظ")}</p>
                      {loadingWallets ? (
                        <p style={{ color: "#aaa", fontSize: "13px" }}>{tr("Loading wallets...", "جارٍ تحميل المحافظ...")}</p>
                      ) : wallets.length === 0 ? (
                        <p style={{ color: "#aaa", fontSize: "13px" }}>{tr("No wallets found.", "لا توجد محافظ.")}</p>
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                          {wallets.map((w) => (
                            <div key={w.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 14px", borderRadius: "12px", backgroundColor: "#fff", border: "1px solid #EEF1F4" }}>
                              <div>
                                <p style={{ fontWeight: "700", color: "#0F172A", fontSize: "13px" }}>{w.currency}</p>
                                <p style={{ fontSize: "11px", color: "#9CA3AF" }}>
                                  {w.account_number ?? w.iban ?? tr(`Wallet #${w.id}`, `محفظة رقم ${w.id}`)}
                                </p>
                              </div>
                              <div style={{ textAlign: "right", display: "flex", alignItems: "center", gap: "12px" }}>
                                <p style={{ fontWeight: "700", color: "#0F172A", fontSize: "14px" }}>{Number(w.balance).toLocaleString()}</p>
                                {canAdjust && (
                                  <button
                                    onClick={() => adjustWallet(w)}
                                    disabled={adjustingId === w.id}
                                    style={{ padding: "7px 12px", borderRadius: "10px", border: "1.5px solid #0F172A", backgroundColor: "#fff", color: "#0F172A", fontSize: "11px", fontWeight: "700", cursor: adjustingId === w.id ? "not-allowed" : "pointer" }}
                                  >
                                    {adjustingId === w.id ? tr("Working...", "جارٍ التنفيذ...") : tr("Adjust", "تعديل الرصيد")}
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
