const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:7777";

export async function fetchAPI(path: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export function wsURL(path: string) {
  const base = API_BASE.replace("http", "ws");
  return `${base}${path}`;
}
