/** Shared token helpers for the shell and remotes. */

export const TOKEN_KEY = "fq_access";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

export function graphqlUrl(): string {
  return process.env.NEXT_PUBLIC_GRAPHQL_URL ?? "http://127.0.0.1:4000/graphql";
}

export function apiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
}

export function trackingWs(): string {
  return process.env.NEXT_PUBLIC_TRACKING_WS ?? "ws://127.0.0.1:8001";
}

export { escapeHtml, sanitizeText } from "../sanitize/index";
