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
      <h2>{sanitizeText("Drivers remote")}</h2>
      <p>
        {sanitizeText("Fleet MFE. Auth token is the Core JWT in localStorage (fq_access).")}
      </p>
    </main>
  );
}
