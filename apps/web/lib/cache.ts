/** HTTP GET response cache used by ApiClient interceptors. */

export type CacheEntry = { data: unknown; expiresAt: number };

export class HttpCache {
  private store = new Map<string, CacheEntry>();

  key(method: string, path: string, body?: BodyInit | null) {
    return `${method}:${path}:${typeof body === "string" ? body : ""}`;
  }

  get(key: string): unknown | undefined {
    const hit = this.store.get(key);
    if (!hit) return undefined;
    if (hit.expiresAt <= Date.now()) {
      this.store.delete(key);
      return undefined;
    }
    return hit.data;
  }

  set(key: string, data: unknown, ttlMs = 30_000) {
    this.store.set(key, { data, expiresAt: Date.now() + ttlMs });
  }

  invalidate(pattern: string) {
    for (const key of [...this.store.keys()]) {
      if (key.includes(pattern)) this.store.delete(key);
    }
  }
}

export const httpCache = new HttpCache();
