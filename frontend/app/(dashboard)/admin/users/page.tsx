"use client";

import { useState } from "react";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";

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
  admin: { bg: "#EEF2FF", fg: "#3730A3" },
  compliance_officer: { bg: "#ECFEFF", fg: "#0E7490" },
  customer: { bg: "#F3F4F6", fg: "#4B5563" },
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

const card: React.CSSProperties = {
  backgroundColor: "#fff",
  border: "1px solid #EEF1F4",
  borderRadius: "16px",
};

export default function AdminUsersPage() {
  const adminName = useAuthStore((s) => s.user?.full_name);
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
      else setError("Search failed.");
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
      setError("Failed to load wallets.");
    } finally {
      setLoadingWallets(false);
    }
  };

  const adjustWallet = async (wallet: WalletItem) => {
    const direction = window.prompt("Direction? Type \"credit\" or \"debit\"");
    if (direction !== "credit" && direction !== "debit") return;
    const amountStr = window.prompt(`Amount (${wallet.currency}):`);
    if (!amountStr) return;
    const amount = Number(amountStr);
    if (!amount || amount <= 0) { setError("Invalid amount."); return; }
    const reason = window.prompt("Reason for adjustment:");
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
      setError(typeof detail === "string" ? detail : "Adjustment failed.");
    } finally {
      setAdjustingId(null);
    }
  };

  const toggleUserStatus = async (user: UserSearchItem) => {
    const suspending = user.is_active;
    if (!window.confirm(suspending ? `Suspend ${user.full_name}? They won't be able to log in until reactivated.` : `Reactivate ${user.full_name}?`)) {
      return;
    }
    setStatusUpdatingId(user.id);
    setError("");
    try {
      const res = await api.post(`/admin/users/${user.id}/${suspending ? "suspend" : "activate"}`);
      setResults((prev) => prev.map((u) => (u.id === user.id ? { ...u, is_active: res.data.is_active } : u)));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not update account status.");
    } finally {
      setStatusUpdatingId(null);
    }
  };

  if (forbidden) {
    return (
      <div style={{ minHeight: "100vh", backgroundColor: "#F7F8FA", padding: "20px" }}>
        <div style={{ ...card, padding: "32px", textAlign: "center", maxWidth: "420px", margin: "80px auto" }}>
          <p style={{ fontWeight: "700", color: "#000", marginBottom: "8px" }}>Compliance access required</p>
          <p style={{ color: "#999", fontSize: "13px" }}>Your account needs the compliance_officer or admin role to look up users.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F7F8FA", padding: "24px 28px 80px" }}>
      {/* Console header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "24px", flexWrap: "wrap", gap: "12px" }}>
        <div>
          <p style={{ color: "#9CA3AF", fontSize: "12px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: "4px" }}>Compliance console</p>
          <h1 style={{ fontSize: "22px", fontWeight: "800", color: "#0F172A", margin: 0 }}>Users</h1>
          <p style={{ color: "#6B7280", fontSize: "13px", marginTop: "4px" }}>Look up accounts, inspect wallets, and manage account status.</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", backgroundColor: "#fff", border: "1px solid #EEF1F4", borderRadius: "999px", padding: "6px 14px 6px 6px" }}>
          <div style={{ width: "28px", height: "28px", borderRadius: "50%", backgroundColor: "#0F172A", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "11px", fontWeight: "700" }}>
            {initials(adminName ?? "Admin")}
          </div>
          <span style={{ fontSize: "12px", fontWeight: "700", color: "#0F172A" }}>{adminName ?? "Admin"}</span>
          <span style={{ fontSize: "10px", fontWeight: "700", color: "#00A844", backgroundColor: "#F0FDF4", borderRadius: "999px", padding: "2px 8px" }}>STAFF</span>
        </div>
      </div>

      {/* Search */}
      <form onSubmit={search} style={{ display: "flex", gap: "8px", marginBottom: "20px" }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name, phone, or account number"
          style={{ flex: 1, padding: "12px 16px", borderRadius: "14px", border: "1.5px solid #E5E7EB", fontSize: "14px", backgroundColor: "#fff" }}
        />
        <button type="submit" disabled={searching}
          style={{ padding: "12px 24px", borderRadius: "14px", border: "none", backgroundColor: "#0F172A", color: "#fff", fontSize: "14px", fontWeight: "700", cursor: searching ? "not-allowed" : "pointer" }}>
          {searching ? "Searching…" : "Search"}
        </button>
      </form>

      {error && (
        <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "12px", padding: "12px", color: "#DC2626", fontSize: "13px", marginBottom: "16px" }}>
          {error}
        </div>
      )}

      {/* Results table */}
      {searched && (
        <div style={{ ...card, overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: "2.4fr 1fr 1fr 1fr 1.8fr", gap: "12px", padding: "12px 20px", borderBottom: "1px solid #EEF1F4", backgroundColor: "#FAFBFC" }}>
            {["Account", "Role", "KYC", "Status", ""].map((h) => (
              <p key={h} style={{ fontSize: "11px", fontWeight: "700", color: "#9CA3AF", textTransform: "uppercase", letterSpacing: "0.4px" }}>{h}</p>
            ))}
          </div>

          {results.length === 0 ? (
            <div style={{ padding: "48px", textAlign: "center" }}>
              <p style={{ color: "#aaa", fontSize: "14px" }}>No accounts match &quot;{query}&quot;.</p>
            </div>
          ) : (
            results.map((u) => {
              const isExpanded = expandedId === u.id;
              const roleColors = ROLE_BADGE_COLORS[u.role] ?? ROLE_BADGE_COLORS.customer;
              const kycColors = KYC_BADGE_COLORS[u.kyc_status] ?? KYC_BADGE_COLORS.not_submitted;
              return (
                <div key={u.id} style={{ borderBottom: "1px solid #F3F4F6" }}>
                  <div
                    onClick={() => toggleRow(u)}
                    style={{ display: "grid", gridTemplateColumns: "2.4fr 1fr 1fr 1fr 1.8fr", gap: "12px", padding: "14px 20px", alignItems: "center", cursor: "pointer" }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
                      <div style={{ width: "34px", height: "34px", borderRadius: "50%", backgroundColor: "#EEF2FF", color: "#3730A3", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "12px", fontWeight: "700", flexShrink: 0 }}>
                        {initials(u.full_name)}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <p style={{ fontWeight: "700", color: "#0F172A", fontSize: "13px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{u.full_name}</p>
                        <p style={{ fontSize: "11px", color: "#9CA3AF", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{u.email} &middot; {u.phone}</p>
                      </div>
                    </div>
                    <span style={{ fontSize: "11px", fontWeight: "700", padding: "4px 10px", borderRadius: "999px", backgroundColor: roleColors.bg, color: roleColors.fg, width: "fit-content", textTransform: "capitalize" }}>
                      {u.role.replaceAll("_", " ")}
                    </span>
                    <span style={{ fontSize: "11px", fontWeight: "700", padding: "4px 10px", borderRadius: "999px", backgroundColor: kycColors.bg, color: kycColors.fg, width: "fit-content", textTransform: "capitalize" }}>
                      {u.kyc_status.replaceAll("_", " ")}
                    </span>
                    <span style={{ fontSize: "11px", fontWeight: "700", padding: "4px 10px", borderRadius: "999px", backgroundColor: u.is_active ? "#F0FDF4" : "#FEF2F2", color: u.is_active ? "#00A844" : "#DC2626", width: "fit-content" }}>
                      {u.is_active ? "Active" : "Suspended"}
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
                          {statusUpdatingId === u.id ? "Working…" : u.is_active ? "Suspend" : "Reactivate"}
                        </button>
                      )}
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" style={{ transform: isExpanded ? "rotate(180deg)" : "none", transition: "transform 0.15s", flexShrink: 0 }}>
                        <path d="M6 9l6 6 6-6" stroke="#9CA3AF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </div>
                  </div>

                  {isExpanded && (
                    <div style={{ padding: "0 20px 20px", backgroundColor: "#FAFBFC" }}>
                      <p style={{ fontSize: "11px", fontWeight: "700", color: "#9CA3AF", textTransform: "uppercase", letterSpacing: "0.4px", marginBottom: "10px", paddingTop: "4px" }}>Wallets</p>
                      {loadingWallets ? (
                        <p style={{ color: "#aaa", fontSize: "13px" }}>Loading wallets…</p>
                      ) : wallets.length === 0 ? (
                        <p style={{ color: "#aaa", fontSize: "13px" }}>No wallets found.</p>
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                          {wallets.map((w) => (
                            <div key={w.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 14px", borderRadius: "12px", backgroundColor: "#fff", border: "1px solid #EEF1F4" }}>
                              <div>
                                <p style={{ fontWeight: "700", color: "#0F172A", fontSize: "13px" }}>{w.currency}</p>
                                <p style={{ fontSize: "11px", color: "#9CA3AF" }}>
                                  {w.account_number ?? w.iban ?? `Wallet #${w.id}`}
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
                                    {adjustingId === w.id ? "Working…" : "Adjust"}
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
