"use client";

const TAGS = /<[^>]*>/g;

function sanitizeText(value: unknown, maxLen = 200): string {
  if (value == null) return "";
  const text = String(value).replace(TAGS, "").trim();
  return text.length > maxLen ? text.slice(0, maxLen) : text;
}

export default function Page() {
  return (
    <main>
      <h2>{sanitizeText("AI remote")}</h2>
      <p>{sanitizeText("Operations agent UI. Uses CORE / AI GraphQL via the gateway.")}</p>
    </main>
  );
}
