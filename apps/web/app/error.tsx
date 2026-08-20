"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="card" style={{ margin: "24px 0", padding: 24 }}>
      <h2>Something went wrong</h2>
      <p className="err">{error.message || "Unexpected error"}</p>
      <button className="ghost" type="button" onClick={() => reset()}>
        Try again
      </button>
    </div>
  );
}
