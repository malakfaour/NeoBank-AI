"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

interface SelfieCaptureProps {
  capturedSelfie?: File;
  hasSavedSelfie?: boolean;
  onCapture: (selfie: File) => void;
  onRetake: () => void;
}

export default function SelfieCapture({
  capturedSelfie,
  hasSavedSelfie = false,
  onCapture,
  onRetake,
}: SelfieCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const [replacingSavedSelfie, setReplacingSavedSelfie] = useState(false);
  const [error, setError] = useState("");

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCameraActive(false);
    setCameraReady(false);
  }, []);

  const startCamera = useCallback(async () => {
    setError("");
    setCameraReady(false);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setCameraActive(true);
    } catch {
      setError("Camera access was denied. Allow camera access to capture your selfie.");
    }
  }, []);

  const preview = useMemo(
    () => capturedSelfie ? URL.createObjectURL(capturedSelfie) : null,
    [capturedSelfie],
  );

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  useEffect(() => {
    if (capturedSelfie || (hasSavedSelfie && !replacingSavedSelfie)) return;
    const timer = window.setTimeout(() => void startCamera(), 0);
    return () => {
      window.clearTimeout(timer);
      stopCamera();
    };
  }, [
    capturedSelfie,
    hasSavedSelfie,
    replacingSavedSelfie,
    startCamera,
    stopCamera,
  ]);

  useEffect(() => () => stopCamera(), [stopCamera]);

  const markCameraReady = () => {
    const video = videoRef.current;
    if (video && video.videoWidth > 0 && video.videoHeight > 0) {
      setCameraReady(true);
    }
  };

  const captureSelfie = () => {
    const video = videoRef.current;
    if (!video?.videoWidth || !video.videoHeight) {
      setError("Camera is not ready yet. Please wait a moment and try again.");
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) {
        setError("The selfie could not be captured. Please try again.");
        return;
      }
      onCapture(new File([blob], "selfie.jpg", { type: "image/jpeg" }));
      setReplacingSavedSelfie(false);
      stopCamera();
    }, "image/jpeg", 0.92);
  };

  const retake = () => {
    setReplacingSavedSelfie(true);
    onRetake();
  };

  if (hasSavedSelfie && !capturedSelfie && !replacingSavedSelfie) {
    return (
      <section aria-label="Selfie capture" style={{ display: "grid", gap: 10 }}>
        <span style={{ color: "#00A844" }}>Selfie already captured securely</span>
        <button type="button" onClick={retake} style={buttonStyle}>
          Capture a new selfie
        </button>
      </section>
    );
  }

  return (
    <section aria-label="Selfie capture" style={{ display: "grid", gap: 10 }}>
      {error && <span role="alert" style={{ color: "#B91C1C" }}>{error}</span>}
      {preview ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={preview}
            alt="Captured selfie preview"
            style={{ width: "100%", maxHeight: 360, objectFit: "cover", borderRadius: 20 }}
          />
          <button type="button" onClick={retake} style={buttonStyle}>Retake selfie</button>
        </>
      ) : (
        <div style={{ position: "relative", overflow: "hidden", borderRadius: 20, background: "#111", aspectRatio: "4 / 3", width: "100%" }}>
          <video
            ref={videoRef}
            aria-label="Live camera preview"
            autoPlay
            playsInline
            muted
            onLoadedMetadata={markCameraReady}
            onCanPlay={markCameraReady}
            style={{ width: "100%", height: "100%", objectFit: "contain" }}
          />
          {cameraActive && (
            <>
              <div
                aria-hidden="true"
                data-testid="selfie-face-guide"
                style={{
                  position: "absolute",
                  height: "65%",
                  aspectRatio: "3 / 4",
                  borderRadius: "50%",
                  border: "3px dashed #00C853",
                  top: "50%",
                  left: "50%",
                  transform: "translate(-50%, -50%)",
                  pointerEvents: "none",
                }}
              />
              {cameraReady ? (
                <button
                  type="button"
                  aria-label="Capture selfie"
                  onClick={captureSelfie}
                  style={{ position: "absolute", bottom: 18, left: "50%", transform: "translateX(-50%)", width: 64, height: 64, borderRadius: "50%", border: "4px solid white", background: "#00C853", cursor: "pointer" }}
                />
              ) : (
                <span style={{ position: "absolute", bottom: 20, left: "50%", transform: "translateX(-50%)", color: "white", background: "rgba(0,0,0,.55)", padding: "6px 12px", borderRadius: 99, whiteSpace: "nowrap" }}>
                  Starting camera…
                </span>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

const buttonStyle: React.CSSProperties = {
  padding: "12px 14px",
  borderRadius: 12,
  border: "1px solid #E5E7EB",
  background: "#fff",
  color: "#111",
  fontWeight: 600,
  cursor: "pointer",
};
