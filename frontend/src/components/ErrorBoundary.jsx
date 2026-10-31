import { Component } from "react";

// A card or the whole app must never become a blank screen: a rendering bug shows `fallback` (default: nothing) and the chat carries on.
export default class ErrorBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error) { console.warn("render failed:", error?.message); } // type of problem only, never user text
  render() { return this.state.failed ? (this.props.fallback ?? null) : this.props.children; }
}
