import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import "./styles.css";

// Last line of defence: if rendering ever fails, show a way back instead of a blank page.
const reload = (
  <div className="crash" role="alert">
    <p>Something went wrong showing this page.</p>
    <button type="button" onClick={() => location.reload()}>Reload</button>
  </div>
);
createRoot(document.getElementById("root")).render(<ErrorBoundary fallback={reload}><App /></ErrorBoundary>);
