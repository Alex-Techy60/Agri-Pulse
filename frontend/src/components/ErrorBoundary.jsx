import { Component } from "react";

// A card or the whole app must never become a blank screen: a rendering bug shows `fallback` (or a styled reload card) and the app carries on.
export default class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    console.warn("render failed:", error?.message);
  }

  render() {
    if (this.state.failed) {
      if (this.props.fallback !== undefined) {
        return this.props.fallback;
      }
      return (
        <div
          className="card error-boundary-card"
          role="alert"
          style={{
            margin: "2rem auto",
            maxWidth: "600px",
            padding: "1.75rem",
            textAlign: "center",
            border: "1px solid rgba(239, 68, 68, 0.35)",
            borderRadius: "1rem",
            background: "rgba(17, 28, 36, 0.95)",
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)"
          }}
        >
          <div style={{ fontSize: "2.5rem", marginBottom: "0.75rem" }}>🌾⚠️</div>
          <h3 style={{ margin: "0 0 0.5rem 0", color: "#fca5a5", fontSize: "1.25rem" }}>
            Something went wrong displaying this section
          </h3>
          <p style={{ margin: "0 0 1.25rem 0", color: "#94a3b8", fontSize: "0.95rem", lineHeight: "1.5" }}>
            An unexpected error occurred while rendering this view. Your farm profile, live data, and active session are preserved.
          </p>
          <div style={{ display: "flex", gap: "0.75rem", justifyContent: "center" }}>
            <button
              type="button"
              className="fnav-btn active"
              onClick={() => this.setState({ failed: false })}
              style={{
                padding: "0.6rem 1.5rem",
                borderRadius: "0.75rem",
                cursor: "pointer",
                background: "#15803d",
                color: "#ffffff",
                border: "none",
                fontWeight: 600
              }}
            >
              ↻ Reload This Section
            </button>
            <button
              type="button"
              className="fnav-btn"
              onClick={() => window.location.reload()}
              style={{
                padding: "0.6rem 1.25rem",
                borderRadius: "0.75rem",
                cursor: "pointer",
                border: "1px solid #334155",
                background: "transparent",
                color: "#cbd5e1"
              }}
            >
              Refresh Entire App
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

