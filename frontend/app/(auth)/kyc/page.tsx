"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import { getPostAuthDestination } from "@/lib/postAuthNavigation";

type Step = "selfie" | "document_type" | "id_upload" | "status";
type KYCStatus = "pending" | "approved" | "rejected" | "flagged";
export type KYCDocumentType = "passport" | "drivers_license" | "national_id";

// Layout moved outside component to fix ESLint error
function KYCLayout({ stepNum, title, subtitle, children }: {
  stepNum: number; title: string; subtitle: string; children: React.ReactNode;
}) {
  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "20px" }}>
      <div style={{ marginBottom: "24px", textAlign: "center" }}>
       <img src="/logo.svg" alt="NeoBank Lebanon" style={{ width: "160px", height: "auto" }} />
        <div style={{ display: "flex", justifyContent: "center", gap: "8px", marginTop: "16px" }}>
          {[1, 2, 3, 4].map((s) => (
            <div key={s} style={{ height: "6px", borderRadius: "999px", backgroundColor: s <= stepNum ? "#00C853" : "#E5E7EB", width: s === stepNum ? "32px" : "16px", transition: "all 0.3s" }} />
          ))}
        </div>
      </div>
      <div style={{ width: "100%", maxWidth: "380px", backgroundColor: "#fff", borderRadius: "24px", padding: "28px", boxShadow: "0 2px 20px rgba(0,0,0,0.08)" }}>
        <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#000", marginBottom: "4px" }}>{title}</h2>
        <p style={{ color: "#999", fontSize: "14px", marginBottom: "20px" }}>{subtitle}</p>
        {children}
      </div>
    </div>
  );
}

function ErrorBanner({ msg }: { msg: string }) {
  return (
    <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "12px", padding: "12px", color: "#DC2626", fontSize: "13px", marginBottom: "16px" }}>
      {msg}
    </div>
  );
}

const DOCUMENT_TYPE_OPTIONS: { value: KYCDocumentType; label: string; icon: string }[] = [
  { value: "passport", label: "Passport", icon: "🛂" },
  { value: "drivers_license", label: "Driver's License", icon: "🚗" },
  { value: "national_id", label: "National ID", icon: "🪪" },
];

export function DocumentTypeSelection({
  selected,
  onSelect,
  onBack,
  onContinue,
}: {
  selected: KYCDocumentType | null;
  onSelect: (documentType: KYCDocumentType) => void;
  onBack: () => void;
  onContinue: () => void;
}) {
  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {DOCUMENT_TYPE_OPTIONS.map((option) => {
          const isSelected = selected === option.value;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onSelect(option.value)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                width: "100%",
                padding: "16px",
                borderRadius: "16px",
                border: `2px solid ${isSelected ? "#00C853" : "#E5E7EB"}`,
                backgroundColor: isSelected ? "#F0FDF4" : "#fff",
                color: "#111",
                fontSize: "15px",
                fontWeight: "600",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <span aria-hidden="true" style={{ fontSize: "24px" }}>{option.icon}</span>
              {option.label}
            </button>
          );
        })}
      </div>
      <div style={{ display: "flex", gap: "12px", marginTop: "16px" }}>
        <button type="button" onClick={onBack}
          style={{ flex: 1, padding: "13px", borderRadius: "14px", border: "1.5px solid #E5E7EB", backgroundColor: "#fff", fontSize: "14px", fontWeight: "600", cursor: "pointer" }}>
          Back
        </button>
        <button type="button" onClick={onContinue} disabled={!selected}
          style={{ flex: 1, padding: "13px", borderRadius: "14px", border: "none", backgroundColor: selected ? "#00C853" : "#E5E7EB", color: selected ? "#fff" : "#999", fontSize: "14px", fontWeight: "700", cursor: selected ? "pointer" : "not-allowed" }}>
          Continue
        </button>
      </div>
    </>
  );
}

export default function KYCPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("selfie");
  const [selfieBlob, setSelfieBlob] = useState<Blob | null>(null);
  const [selfiePreview, setSelfiePreview] = useState<string | null>(null);
  const [idFile, setIdFile] = useState<File | null>(null);
  const [idPreview, setIdPreview] = useState<string | null>(null);
  const [documentType, setDocumentType] = useState<KYCDocumentType | null>(null);
  const [status, setStatus] = useState<KYCStatus>("pending");
  const [rejectionReason, setRejectionReason] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [cameraActive, setCameraActive] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    void getPostAuthDestination().then((destination) => {
      if (destination !== "/kyc") router.replace(destination);
    });
    api.get("/auth/status").then((response) => {
      if (response.data.kyc_onboarding_state === "rejected") {
        setStatus("rejected");
        setRejectionReason(response.data.kyc_rejection_reason ?? "");
        setStep("status");
      }
    }).catch(() => {});
  }, [router]);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCameraActive(false);
  }, []);

  const startCamera = useCallback(async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setCameraActive(true);
    } catch { setError("Camera access denied."); }
  }, []);

useEffect(() => {
  if (step !== "selfie") return;
  const timer = setTimeout(() => { startCamera(); }, 0);
  return () => { clearTimeout(timer); stopCamera(); };
}, [step, startCamera, stopCamera]);

  useEffect(() => () => { clearInterval(pollRef.current!); }, []);

  const captureSelfie = () => {
    if (!videoRef.current) return;
    const canvas = document.createElement("canvas");
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    canvas.getContext("2d")?.drawImage(videoRef.current, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return;
      setSelfieBlob(blob);
      setSelfiePreview(URL.createObjectURL(blob));
      stopCamera();
    }, "image/jpeg");
  };

  const handleUpload = async () => {
    if (!selfieBlob || !idFile || !documentType) { setError("Selfie, document type, and ID are required."); return; }
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("selfie", selfieBlob, "selfie.jpg");
      form.append("id_photo", idFile);
      form.append("document_type", documentType);
      await api.post("/kyc/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
      setStep("status");
      pollRef.current = setInterval(async () => {
        try {
          const res = await api.get("/kyc/status");
          const s: KYCStatus = res.data.kyc_status;
          setStatus(s);
          if (s === "approved") { clearInterval(pollRef.current!); setTimeout(() => router.push("/dashboard"), 2000); }
          else if (s === "rejected") clearInterval(pollRef.current!);
        } catch { /* ignore poll errors */ }
      }, 5000);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Upload failed.";
      setError(message);
    } finally { setUploading(false); }
  };

  if (step === "selfie") return (
    <KYCLayout stepNum={1} title="Take a selfie" subtitle="Make sure your face is clearly visible and well lit.">
      {error && <ErrorBanner msg={error} />}
      {!selfiePreview ? (
        <div style={{ position: "relative", borderRadius: "20px", overflow: "hidden", backgroundColor: "#F5F5F5", aspectRatio: "3/4", width: "100%" }}>
          <video ref={videoRef} autoPlay playsInline muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          {cameraActive && (
            <>
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
                <div style={{ width: "180px", height: "240px", borderRadius: "50%", border: "2px dashed #00C853", opacity: 0.7 }} />
              </div>
              <button onClick={captureSelfie} style={{ position: "absolute", bottom: "20px", left: "50%", transform: "translateX(-50%)", width: "64px", height: "64px", borderRadius: "50%", backgroundColor: "#00C853", border: "4px solid #fff", cursor: "pointer", boxShadow: "0 4px 12px rgba(0,0,0,0.2)" }} />
            </>
          )}
        </div>
      ) : (
        <div>
          <div style={{ borderRadius: "20px", overflow: "hidden", aspectRatio: "3/4" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={selfiePreview} alt="Selfie preview" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          </div>
          <div style={{ display: "flex", gap: "12px", marginTop: "16px" }}>
            <button onClick={() => { setSelfieBlob(null); setSelfiePreview(null); startCamera(); }}
              style={{ flex: 1, padding: "13px", borderRadius: "14px", border: "1.5px solid #E5E7EB", backgroundColor: "#fff", fontSize: "14px", fontWeight: "600", cursor: "pointer" }}>
              Retake
            </button>
            <button onClick={() => setStep("document_type")}
              style={{ flex: 1, padding: "13px", borderRadius: "14px", border: "none", backgroundColor: "#00C853", color: "#fff", fontSize: "14px", fontWeight: "700", cursor: "pointer" }}>
              Use this photo
            </button>
          </div>
        </div>
      )}
    </KYCLayout>
  );

  if (step === "document_type") return (
    <KYCLayout stepNum={2} title="Choose your document" subtitle="Select the type of identity document you will upload.">
      <DocumentTypeSelection
        selected={documentType}
        onSelect={setDocumentType}
        onBack={() => setStep("selfie")}
        onContinue={() => setStep("id_upload")}
      />
    </KYCLayout>
  );

  if (step === "id_upload") return (
    <KYCLayout stepNum={3} title="Upload your ID" subtitle="Take a clear photo of your selected identity document.">
      {error && <ErrorBanner msg={error} />}
      <label style={{ display: "block", width: "100%", borderRadius: "20px", border: `2px dashed ${idPreview ? "#00C853" : "#E5E7EB"}`, cursor: "pointer", overflow: "hidden" }}>
        <input type="file" accept="image/*" style={{ display: "none" }} onChange={(e) => {
          const f = e.target.files?.[0]; if (!f) return;
          setIdFile(f); setIdPreview(URL.createObjectURL(f)); setError("");
        }} />
        {idPreview
          ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={idPreview} alt="ID preview" style={{ width: "100%", maxHeight: "220px", objectFit: "cover" }} />
          )
          : (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "48px 20px", gap: "8px" }}>
              <div style={{ fontSize: "32px" }}>🪪</div>
              <p style={{ color: "#666", fontSize: "14px" }}>Tap to upload ID photo</p>
              <p style={{ color: "#aaa", fontSize: "12px" }}>JPG, PNG — max 10 MB</p>
            </div>
          )
        }
      </label>
      {idPreview && <p style={{ color: "#00C853", fontSize: "13px", textAlign: "center", marginTop: "8px" }}>✓ {idFile?.name}</p>}
      <div style={{ display: "flex", gap: "12px", marginTop: "16px" }}>
        <button onClick={() => { setStep("document_type"); setIdFile(null); setIdPreview(null); }}
          style={{ flex: 1, padding: "13px", borderRadius: "14px", border: "1.5px solid #E5E7EB", backgroundColor: "#fff", fontSize: "14px", fontWeight: "600", cursor: "pointer" }}>
          Back
        </button>
        <button onClick={handleUpload} disabled={!idFile || uploading}
          style={{ flex: 1, padding: "13px", borderRadius: "14px", border: "none", backgroundColor: !idFile || uploading ? "#E5E7EB" : "#00C853", color: !idFile || uploading ? "#999" : "#fff", fontSize: "14px", fontWeight: "700", cursor: !idFile || uploading ? "not-allowed" : "pointer" }}>
          {uploading ? "Uploading..." : "Submit"}
        </button>
      </div>
    </KYCLayout>
  );

  return (
    <KYCLayout stepNum={4} title="Verification status" subtitle="We&apos;re reviewing your documents.">
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "16px", padding: "16px 0" }}>
        {status === "pending" && (
          <>
            <div style={{ width: "64px", height: "64px", borderRadius: "50%", backgroundColor: "#FFFBEB", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "28px" }}>⏳</div>
            <div style={{ textAlign: "center" }}>
              <p style={{ fontWeight: "700", color: "#000" }}>Under review</p>
              <p style={{ color: "#999", fontSize: "13px", marginTop: "4px" }}>This usually takes under a minute.</p>
            </div>
            <div style={{ display: "flex", gap: "6px" }}>
              {[0, 1, 2].map((i) => (
                <div key={i} style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#00C853" }} />
              ))}
            </div>
          </>
        )}
        {status === "approved" && (
          <>
            <div style={{ width: "64px", height: "64px", borderRadius: "50%", backgroundColor: "#F0FDF4", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "28px" }}>✅</div>
            <div style={{ textAlign: "center" }}>
              <p style={{ fontWeight: "700", color: "#000" }}>Identity verified</p>
              <p style={{ color: "#999", fontSize: "13px", marginTop: "4px" }}>Redirecting to your dashboard...</p>
            </div>
          </>
        )}
        {(status === "rejected" || status === "flagged") && (
          <>
            <div style={{ width: "64px", height: "64px", borderRadius: "50%", backgroundColor: "#FEF2F2", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "28px" }}>❌</div>
            <div style={{ textAlign: "center" }}>
              <p style={{ fontWeight: "700", color: "#000" }}>Verification failed</p>
              <p style={{ color: "#999", fontSize: "13px", marginTop: "4px" }}>{status === "flagged" ? "Under manual review." : rejectionReason || "Please try again."}</p>
            </div>
            {status === "rejected" && (
              <button onClick={() => { setStep("selfie"); setSelfieBlob(null); setSelfiePreview(null); setIdFile(null); setIdPreview(null); setDocumentType(null); setStatus("pending"); }}
                style={{ width: "100%", padding: "13px", borderRadius: "14px", border: "none", backgroundColor: "#00C853", color: "#fff", fontSize: "14px", fontWeight: "700", cursor: "pointer" }}>
                Try again
              </button>
            )}
          </>
        )}
      </div>
    </KYCLayout>
  );
}

