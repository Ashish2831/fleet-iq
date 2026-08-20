/** Public API surface for pages — thin re-exports over ApiClient. */

export {
  ApiClient,
  ApiError,
  api,
  clearToken,
  getToken,
  gql,
  rest,
  setToken,
  WS_URL,
} from "./client";
export type { BatchRequest, RequestOptions } from "./client";
export { escapeHtml, sanitizeText } from "./sanitize";
export { useDeferredQuery, useRestQuery } from "./hooks";
