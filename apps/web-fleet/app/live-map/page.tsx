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
      <h2>{sanitizeText("Fleet remote")}</h2>
      <p>
        {sanitizeText(
          "Live map ships from this origin (:3001). Shell rewrites /live-map here when FLEET_MFE_ORIGIN is set.",
        )}
      </p>
    </main>
  );
}
