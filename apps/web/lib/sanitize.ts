/** Client-side XSS hardening for untrusted strings before render / echo. */

const TAGS = /<[^>]*>/g;
const SCRIPTISH = /javascript\s*:|data\s*:|vbscript\s*:|on\w+\s*=/gi;
const CONTROL = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g;

export function sanitizeText(value: unknown, maxLen = 4000): string {
  if (value == null) return "";
  let text = String(value).replace(CONTROL, "").replace(TAGS, "");
  text = text.replace(SCRIPTISH, "");
  if (typeof document !== "undefined") {
    const el = document.createElement("textarea");
    el.innerHTML = text;
    text = el.value;
  }
  text = text.trim();
  return maxLen && text.length > maxLen ? text.slice(0, maxLen) : text;
}

export function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
