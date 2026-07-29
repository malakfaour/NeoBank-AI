"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";

type BeneficiaryType = "mobile" | "iban";

interface Beneficiary {
  id: number;
  nickname: string;
  type: BeneficiaryType;
  value: string;
}

function beneficiaryTypeLabel(type: BeneficiaryType) {
  return type === "mobile" ? "Mobile" : "IBAN";
}

function beneficiarySectionLabel(type: BeneficiaryType) {
  return type === "mobile"
    ? "Mobile beneficiaries"
    : "IBAN beneficiaries";
}

function beneficiarySearchPlaceholder(type: BeneficiaryType) {
  return type === "mobile"
    ? "Search by nickname or mobile number"
    : "Search by nickname or IBAN";
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
        Saved Beneficiaries
      </h1>
    </div>
  );
}

export default function BeneficiariesPage() {
  const router = useRouter();
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
    <main style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px" }}>
      <PageHeader onBack={() => router.back()} />

      <div style={{ display: "flex", gap: "8px", marginBottom: "20px" }}>
        {(["mobile", "iban"] as BeneficiaryType[]).map((type) => (
          <button
            type="button"
            key={type}
            onClick={() => switchType(type)}
            style={{ flex: 1, padding: "10px", borderRadius: "12px", border: "none", backgroundColor: activeType === type ? "#00C853" : "#E5E7EB", color: activeType === type ? "#fff" : "#666", fontWeight: "600", fontSize: "13px", cursor: "pointer" }}
          >
            {beneficiaryTypeLabel(type)}
          </button>
        ))}
      </div>

      <input
        type="search"
        value={search}
        onChange={(event) => {
          setSearch(event.target.value);
          setLoading(true);
          setError("");
        }}
        placeholder={beneficiarySearchPlaceholder(activeType)}
        aria-label="Search beneficiaries"
        style={{
          ...inputStyle,
          backgroundColor: "#fff",
          marginBottom: "14px",
        }}
      />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
        <p style={{ color: "#666", fontSize: "13px", margin: 0 }}>
          {beneficiarySectionLabel(activeType)}
        </p>
        <button
          type="button"
          onClick={() => {
            setShowAddForm((current) => !current);
            setError("");
          }}
          style={{ backgroundColor: "#00C853", color: "#fff", border: "none", borderRadius: "10px", padding: "9px 16px", fontSize: "13px", fontWeight: "700", cursor: "pointer" }}
        >
          {showAddForm ? "Cancel" : "Add"}
        </button>
      </div>

      {showAddForm && (
        <form onSubmit={handleAdd} style={{ backgroundColor: "#fff", borderRadius: "16px", padding: "16px", marginBottom: "14px", display: "flex", flexDirection: "column", gap: "10px" }}>
          <input
            value={nickname}
            onChange={(event) => setNickname(event.target.value)}
            placeholder="Nickname"
            required
            style={inputStyle}
          />
          <input
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={beneficiaryValuePlaceholder(activeType)}
            required
            style={inputStyle}
          />
          <button
            type="submit"
            disabled={actionLoading === "add" || !nickname.trim() || !value.trim()}
            style={{ backgroundColor: actionLoading === "add" ? "#86EFAC" : "#00C853", color: "#fff", border: "none", borderRadius: "12px", padding: "12px", fontSize: "14px", fontWeight: "700", cursor: actionLoading === "add" ? "not-allowed" : "pointer" }}
          >
            {actionLoading === "add" ? "Adding..." : "Add Beneficiary"}
          </button>
        </form>
      )}

      {error && (
        <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>
      )}

      {loading ? (
        <div style={{ backgroundColor: "#fff", borderRadius: "16px", padding: "32px", textAlign: "center" }}>
          <p style={{ color: "#888", fontSize: "14px" }}>Loading beneficiaries...</p>
        </div>
      ) : beneficiaries.length === 0 ? (
        <div style={{ backgroundColor: "#fff", borderRadius: "16px", padding: "32px", textAlign: "center" }}>
          <p style={{ color: "#888", fontSize: "14px" }}>
            {search.trim()
              ? "No beneficiaries match your search."
              : "No saved beneficiaries yet."}
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {beneficiaries.map((beneficiary) => (
            <div key={beneficiary.id} style={{ backgroundColor: "#fff", borderRadius: "16px", padding: "16px" }}>
              {editingId === beneficiary.id ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                  <input
                    value={editNickname}
                    onChange={(event) => setEditNickname(event.target.value)}
                    aria-label={`Rename ${beneficiary.nickname}`}
                    style={inputStyle}
                  />
                  <div style={{ display: "flex", gap: "8px" }}>
                    <button
                      type="button"
                      onClick={() => handleRename(beneficiary.id)}
                      disabled={actionLoading === `edit-${beneficiary.id}` || !editNickname.trim()}
                      style={{ flex: 1, backgroundColor: "#00C853", color: "#fff", border: "none", borderRadius: "10px", padding: "10px", fontWeight: "700", cursor: "pointer" }}
                    >
                      {actionLoading === `edit-${beneficiary.id}` ? "Saving..." : "Save"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setEditingId(null);
                        setEditNickname("");
                      }}
                      style={{ flex: 1, backgroundColor: "#E5E7EB", color: "#555", border: "none", borderRadius: "10px", padding: "10px", fontWeight: "700", cursor: "pointer" }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div style={{ marginBottom: "14px" }}>
                    <p style={{ color: "#000", fontSize: "15px", fontWeight: "700", margin: "0 0 4px" }}>{beneficiary.nickname}</p>
                    <p style={{ color: "#888", fontSize: "13px", margin: 0, wordBreak: "break-all" }}>{beneficiary.value}</p>
                  </div>
                  {confirmDeleteId === beneficiary.id ? (
                    <div style={{ backgroundColor: "#FEF2F2", borderRadius: "10px", padding: "12px" }}>
                      <p style={{ color: "#991B1B", fontSize: "13px", fontWeight: "600", margin: "0 0 10px" }}>Are you sure?</p>
                      <div style={{ display: "flex", gap: "8px" }}>
                        <button
                          type="button"
                          onClick={() => handleDelete(beneficiary.id)}
                          disabled={actionLoading === `delete-${beneficiary.id}`}
                          style={{ flex: 1, backgroundColor: "#EF4444", color: "#fff", border: "none", borderRadius: "9px", padding: "9px", fontWeight: "700", cursor: "pointer" }}
                        >
                          {actionLoading === `delete-${beneficiary.id}` ? "Deleting..." : "Delete"}
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmDeleteId(null)}
                          style={{ flex: 1, backgroundColor: "#fff", color: "#555", border: "1px solid #E5E7EB", borderRadius: "9px", padding: "9px", fontWeight: "700", cursor: "pointer" }}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div style={{ display: "flex", gap: "8px" }}>
                      <button
                        type="button"
                        onClick={() => {
                          setEditingId(beneficiary.id);
                          setEditNickname(beneficiary.nickname);
                          setConfirmDeleteId(null);
                          setError("");
                        }}
                        style={{ flex: 1, backgroundColor: "#F0FDF4", color: "#00A844", border: "none", borderRadius: "10px", padding: "9px", fontWeight: "700", cursor: "pointer" }}
                      >
                        Rename
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setConfirmDeleteId(beneficiary.id);
                          setEditingId(null);
                          setError("");
                        }}
                        style={{ flex: 1, backgroundColor: "#FEF2F2", color: "#EF4444", border: "none", borderRadius: "10px", padding: "9px", fontWeight: "700", cursor: "pointer" }}
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
