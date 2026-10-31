// A link from the API is shown only if it is plain http(s); anything else (javascript:, data:) is rendered as text, never as a link.
export const safeHref = (u) => (/^https?:\/\//i.test(String(u ?? "")) ? String(u) : undefined);
