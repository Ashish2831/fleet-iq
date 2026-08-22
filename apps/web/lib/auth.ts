/** Token helpers + useSyncExternalStore-friendly subscribe. */

export const TOKEN_KEY = "fq_access";
export const AUTH_EVENT = "fq-auth";

function emit() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(AUTH_EVENT));
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
  emit();
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
  emit();
}

export function subscribeAuth(onStoreChange: () => void) {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener("storage", onStoreChange);
  window.addEventListener(AUTH_EVENT, onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener(AUTH_EVENT, onStoreChange);
  };
}

export function getServerAuthSnapshot() {
  return null;
}
