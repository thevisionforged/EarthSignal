/**
 * Where the API lives. Empty (the default) means the same origin as the page: the production server serves the
 * UI and the API together, and `npm run dev` proxies /api. Set VITE_API_BASE at BUILD time only for a split
 * deployment, e.g. VITE_API_BASE=https://api.example.org (the API must then list this site in
 * EARTHSIGNAL_CORS_ORIGINS).
 */
export function joinBase(base: string | undefined, path: string): string {
  return `${(base ?? "").trim().replace(/\/+$/, "")}${path}`;
}

export const apiUrl = (path: string): string => joinBase(import.meta.env.VITE_API_BASE as string | undefined, path);
