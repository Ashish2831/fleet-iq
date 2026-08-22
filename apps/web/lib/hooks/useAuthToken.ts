"use client";

import { useSyncExternalStore } from "react";

import { getServerAuthSnapshot, getToken, subscribeAuth } from "../auth";

/** React 19 / §30 — subscribe to the JWT token store without tearing. */
export function useAuthToken() {
  return useSyncExternalStore(subscribeAuth, getToken, getServerAuthSnapshot);
}
