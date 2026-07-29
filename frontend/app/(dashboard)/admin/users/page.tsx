"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
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

export default function AdminUsersPage() {
  const router = useRouter();
  const role = useAuthStore((s) => s.user?.role);
  const canAdjust = role === "admin";

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserSearchItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [forbidden, setForbidden] = useState(false);

  const [selectedUser, setSelectedUser] = useState<UserSearchItem | null>(null);
  const [wallets, setWallets] = useState<WalletItem[]>([]);
  const [loadingWallets, setLoadingWallets] = useState(false);
  const [adjustingId, setAdjustingId] = useState<number | null>(null);
  const [statusUpdatingId, setStatusUpdatingId] = useState<number | null>(null);

  const search = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setError("");
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

  const selectUser = async (user: UserSearchItem) => {
    setSelectedUser(user);
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
      const updated = { ...user, is_active: res.data.is_active };
      setResults((prev) => prev.map((u) => (u.id === user.id ? updated : u)));
      setSelectedUser((prev) => (prev?.id === user.id ? updated : prev));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not update account status.");
    } finally {
      setStatusUpdatingId(null);
    }
  };

  if (forbidden) {
    return (
      <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px" }}>
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "32px", textAlign: "center", maxWidth: "420px", margin: "80px auto" }}>
          <p style={{ fontWeight: "700", color: "#000", marginBottom: "8px" }}>Compliance access required</p>
          <p style={{ color: "#999", fontSize: "13px" }}>Your account needs the compliance_officer or admin role to look up users.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px", paddingBottom: "80px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "20px" }}>
        <button onClick={() => router.back()}
          style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
        </button>
        <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>Users</h2>
      </div>

      <form onSubmit={search} style={{ display: "flex", gap: "8px", marginBottom: "20px" }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name, email, or phone"
          style={{ flex: 1, padding: "12px 16px", borderRadius: "14px", border: "1.5px solid #E5E7EB", fontSize: "14px", backgroundColor: "#fff" }}
        />
        <button type="submit" disabled={searching}
          style={{ padding: "12px 20px", borderRadius: "14px", border: "none", backgroundColor: "#00C853", color: "#fff", fontSize: "14px", fontWeight: "700", cursor: searching ? "not-allowed" : "pointer" }}>
          {searching ? "Searching..." : "Search"}
        </button>
      </form>

      {error && (
        <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "12px", padding: "12px", color: "#DC2626", fontSize: "13px", marginBottom: "16px" }}>
          {error}
        </div>
      )}

      {results.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "24px" }}>
          {results.map((u) => (
            <button
              key={u.id}
              onClick={() => selectUser(u)}
              style={{
                textAlign: "left",
                backgroundColor: selectedUser?.id === u.id ? "#F0FDF4" : "#fff",
                border: `1.5px solid ${selectedUser?.id === u.id ? "#00C853" : "transparent"}`,
                borderRadius: "16px",
                padding: "16px",
                cursor: "pointer",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <p style={{ fontWeight: "700", color: "#000" }}>{u.full_name}</p>
                  <p style={{ fontSize: "12px", color: "#999" }}>{u.email} &middot; {u.phone}</p>
                </div>
                <div style={{ textAlign: "right" }}>
                  <span style={{ fontSize: "11px", fontWeight: "700", padding: "3px 8px", borderRadius: "999px", backgroundColor: "#F0FDF4", color: "#00C853" }}>
                    {u.role}
                  </span>
                  {!u.is_active && (
                    <span style={{ fontSize: "11px", fontWeight: "700", padding: "3px 8px", borderRadius: "999px", backgroundColor: "#FEF2F2", color: "#DC2626", marginLeft: "6px" }}>
                      Suspended
                    </span>
                  )}
                  <p style={{ fontSize: "11px", color: "#999", marginTop: "4px" }}>KYC: {u.kyc_status}</p>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {selectedUser && (
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
            <p style={{ fontWeight: "700", color: "#000" }}>{selectedUser.full_name}&apos;s wallets</p>
            {canAdjust && (
              <button
                onClick={() => toggleUserStatus(selectedUser)}
                disabled={statusUpdatingId === selectedUser.id}
                style={{
                  padding: "8px 14px",
                  borderRadius: "10px",
                  border: `1.5px solid ${selectedUser.is_active ? "#DC2626" : "#00C853"}`,
                  backgroundColor: "#fff",
                  color: selectedUser.is_active ? "#DC2626" : "#00C853",
                  fontSize: "12px",
                  fontWeight: "700",
                  cursor: statusUpdatingId === selectedUser.id ? "not-allowed" : "pointer",
                }}
              >
                {statusUpdatingId === selectedUser.id ? "Working..." : selectedUser.is_active ? "Suspend account" : "Reactivate account"}
              </button>
            )}
          </div>
          {loadingWallets ? (
            <p style={{ color: "#aaa", fontSize: "14px" }}>Loading wallets...</p>
          ) : wallets.length === 0 ? (
            <p style={{ color: "#aaa", fontSize: "14px" }}>No wallets found.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {wallets.map((w) => (
                <div key={w.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px", borderRadius: "14px", backgroundColor: "#F5F5F5" }}>
                  <div>
                    <p style={{ fontWeight: "700", color: "#000" }}>{w.currency}</p>
                    <p style={{ fontSize: "12px", color: "#999" }}>
                      {w.account_number ?? w.iban ?? `Wallet #${w.id}`}
                    </p>
                  </div>
                  <div style={{ textAlign: "right", display: "flex", alignItems: "center", gap: "12px" }}>
                    <p style={{ fontWeight: "700", color: "#000" }}>{Number(w.balance).toLocaleString()}</p>
                    {canAdjust && (
                      <button
                        onClick={() => adjustWallet(w)}
                        disabled={adjustingId === w.id}
                        style={{ padding: "8px 14px", borderRadius: "10px", border: "1.5px solid #00C853", backgroundColor: "#fff", color: "#00C853", fontSize: "12px", fontWeight: "700", cursor: adjustingId === w.id ? "not-allowed" : "pointer" }}
                      >
                        {adjustingId === w.id ? "Working..." : "Adjust"}
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
}
