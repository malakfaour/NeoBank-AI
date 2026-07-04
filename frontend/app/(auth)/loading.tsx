export default function Loading() {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", backgroundColor: "#F5F5F5" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ width: "36px", height: "36px", borderRadius: "50%", border: "3px solid #00C853", borderTopColor: "transparent", margin: "0 auto 12px", animation: "spin 0.8s linear infinite" }} />
        <p style={{ color: "#aaa", fontSize: "13px" }}>Loading...</p>
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}