/** FleetIQ API client — interceptors, dedup, batch, shared errors. */

import { clearToken, getToken, setToken } from "./auth";
import { httpCache } from "./cache";
import { sanitizeText } from "./sanitize";

export type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

export class ApiError extends Error {
  status: number;
  title?: string;
  code?: string;
  requestId?: string | null;
  body?: unknown;

  constructor(message: string, init: Partial<ApiError> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = init.status ?? 0;
    this.title = init.title;
    this.code = init.code;
    this.requestId = init.requestId;
    this.body = init.body;
  }
}

export type RequestOptions = RequestInit & {
  /** Skip in-flight deduplication for this call */
  dedupe?: boolean;
  /** Skip JSON Content-Type */
  raw?: boolean;
  /** Skip HTTP response cache (GET/GQL) */
  useHttpCache?: boolean;
  /** Cache TTL ms (default 30s) */
  cacheTtlMs?: number;
};

type RequestInterceptor = (path: string, options: RequestOptions) => RequestOptions | Promise<RequestOptions>;
type ResponseInterceptor = (response: Response, path: string) => void | Promise<void>;

export type BatchRequest = { id: string; path: string; method?: "GET" };

class RequestDeduplicator {
  private pending = new Map<string, Promise<unknown>>();

  async run<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
    const existing = this.pending.get(key);
    if (existing) return existing as Promise<T>;
    const promise = fetcher().finally(() => this.pending.delete(key));
    this.pending.set(key, promise);
    return promise;
  }
}

export class ApiClient {
  baseURL: string;
  graphqlURL: string;
  private requestInterceptors: RequestInterceptor[] = [];
  private responseInterceptors: ResponseInterceptor[] = [];
  private deduper = new RequestDeduplicator();

  constructor(baseURL?: string, graphqlURL?: string) {
    this.baseURL = baseURL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
    this.graphqlURL =
      graphqlURL ?? process.env.NEXT_PUBLIC_GRAPHQL_URL ?? `${this.baseURL}/graphql`;

    this.addRequestInterceptor((path, options) => {
      const headers = new Headers(options.headers);
      if (!options.raw && !headers.has("Content-Type") && options.body) {
        headers.set("Content-Type", "application/json");
      }
      const token = getToken();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      if (!headers.has("X-Request-ID")) {
        headers.set("X-Request-ID", crypto.randomUUID?.() ?? `fq-${Date.now()}`);
      }
      return { ...options, headers };
    });

    this.addResponseInterceptor((response) => {
      const cc = response.headers.get("Cache-Control") || "";
      if (/no-store|no-cache/i.test(cc)) {
        httpCache.invalidate(response.url || "");
      }
    });
  }

  addRequestInterceptor(fn: RequestInterceptor) {
    this.requestInterceptors.push(fn);
  }

  addResponseInterceptor(fn: ResponseInterceptor) {
    this.responseInterceptors.push(fn);
  }

  async rest<T>(path: string, init: RequestOptions = {}): Promise<T> {
    const method = (init.method || "GET").toUpperCase();
    const dedupe = init.dedupe !== false && method === "GET";
    const key = httpCache.key(method, path, init.body ?? null);
    const useCache = init.useHttpCache !== false && method === "GET";

    if (useCache) {
      const cached = httpCache.get(key);
      if (cached !== undefined) return cached as T;
    }

    const exec = async () => {
      let options: RequestOptions = { ...init, method };
      for (const interceptor of this.requestInterceptors) {
        options = await interceptor(path, options);
      }
      const res = await fetch(`${this.baseURL}${path}`, options);
      for (const interceptor of this.responseInterceptors) {
        await interceptor(res, path);
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new ApiError(
          sanitizeText(String(data.detail || data.title || res.statusText), 300) || res.statusText,
          {
            status: res.status,
            title: data.title,
            code: data.code,
            requestId: data.request_id ?? res.headers.get("X-Request-ID"),
            body: data,
          },
        );
      }
      if (useCache) httpCache.set(key, data, init.cacheTtlMs ?? 30_000);
      if (method !== "GET") httpCache.invalidate("/api/v1/");
      return data as T;
    };

    return dedupe ? this.deduper.run(key, exec) : exec();
  }

  async gql<T>(query: string, variables?: Record<string, unknown>): Promise<T> {
    const key = `GQL:${query}:${JSON.stringify(variables ?? {})}`;
    const isMutation = /^\s*mutation\b/i.test(query);
    if (!isMutation) {
      const cached = httpCache.get(key);
      if (cached !== undefined) return cached as T;
    }
    return this.deduper.run(key, async () => {
      let options: RequestOptions = {
        method: "POST",
        body: JSON.stringify({ query, variables }),
      };
      for (const interceptor of this.requestInterceptors) {
        options = await interceptor("/graphql", options);
      }
      const res = await fetch(this.graphqlURL, options);
      for (const interceptor of this.responseInterceptors) {
        await interceptor(res, "/graphql");
      }
      const body = await res.json();
      if (body.errors?.length) {
        throw new ApiError(sanitizeText(String(body.errors[0].message), 300), {
          status: res.status || 400,
          body,
        });
      }
      if (isMutation) httpCache.invalidate("GQL:");
      else httpCache.set(key, body.data, 30_000);
      return body.data as T;
    });
  }

  async batch(requests: BatchRequest[]): Promise<Record<string, unknown>> {
    const result = await this.rest<{
      success: boolean;
      responses: Array<{ id: string; success: boolean; data?: unknown; error?: unknown }>;
    }>("/api/v1/batch", {
      method: "POST",
      body: JSON.stringify({ requests }),
      dedupe: false,
    });
    const byId: Record<string, unknown> = {};
    for (const row of result.responses || []) {
      byId[row.id] = row.success ? row.data : { error: row.error };
    }
    return byId;
  }
}

export const api = new ApiClient();

export const WS_URL =
  process.env.NEXT_PUBLIC_TRACKING_WS ?? process.env.NEXT_PUBLIC_WS_URL ?? "ws://127.0.0.1:8000";

export { clearToken, getToken, setToken };

export async function rest<T>(path: string, init: RequestOptions = {}): Promise<T> {
  return api.rest<T>(path, init);
}

export async function gql<T>(query: string, variables?: Record<string, unknown>): Promise<T> {
  return api.gql<T>(query, variables);
}
