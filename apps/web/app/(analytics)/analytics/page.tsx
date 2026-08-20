import { sanitizeText } from "@fleetiq/sanitize";

export default function AnalyticsPage() {
  return (
    <>
      <h2>{sanitizeText("Analytics")}</h2>
      <p className="muted">
        {sanitizeText(
          "KPI projections land in Phase I / Analytics service. Dashboard counts are GraphQL today.",
        )}
      </p>
    </>
  );
}
