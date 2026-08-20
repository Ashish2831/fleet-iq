"use client";

const TAGS = /<[^>]*>/g;

function sanitizeText(value: unknown, maxLen = 200): string {
  if (value == null) return "";
  const text = String(value).replace(TAGS, "").trim();
  return text.length > maxLen ? text.slice(0, maxLen) : text;
}

export default function Page() {
  const title = sanitizeText("Orders remote");
  return (
    <main>
      <h2>{title}</h2>
      <p>{sanitizeText("Orders MFE on :3002. Shell rewrites /orders here when ORDERS_MFE_ORIGIN is set.")}</p>
    </main>
  );
}
