"use client";

import { useDeferredValue, useEffect, useState, useTransition } from "react";

import { api } from "./client";
import { sanitizeText } from "./sanitize";

/** Debounced / deferred search string for non-urgent filter updates. */
export function useDeferredQuery(initial = "") {
  const [query, setQuery] = useState(initial);
  const deferred = useDeferredValue(query);
  const [isPending, startTransition] = useTransition();

  function update(next: string) {
    startTransition(() => setQuery(sanitizeText(next, 200)));
  }

  return { query, deferredQuery: deferred, setQuery: update, isPending };
}

/** Fetch once on mount (GET deduped by ApiClient). */
export function useRestQuery<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setLoading(true);
    api
      .rest<T>(path)
      .then((value) => {
        if (!cancelled) {
          setData(value);
          setError(null);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(sanitizeText(err.message, 200));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  return { data, error, loading };
}
