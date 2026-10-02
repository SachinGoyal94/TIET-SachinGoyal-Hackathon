/** Thin typed fetch wrapper. In dev, Vite proxies /api to the engine;
 *  in production the engine serves this bundle from the same origin. */

import type { Health } from "./types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<Health>("/health"),
};
