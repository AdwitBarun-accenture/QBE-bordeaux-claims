// Thin fetch wrapper: adds the JWT, parses JSON, surfaces API error messages.
const BASE = import.meta.env.VITE_API_BASE || "";
let token = sessionStorage.getItem("bdx_token") || "";

export function setToken(t) {
  token = t || "";
  if (t) sessionStorage.setItem("bdx_token", t);
  else sessionStorage.removeItem("bdx_token");
}

async function request(method, path, body, isForm = false) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  if (body && !isForm) headers["Content-Type"] = "application/json";
  const res = await fetch(BASE + path, {
    method,
    headers,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });
  if (res.status === 401) {
    setToken("");
    window.dispatchEvent(new Event("bdx-logout"));
  }
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) throw new Error((data && data.detail) || `Request failed (${res.status})`);
  return data;
}

export const api = {
  get: (p) => request("GET", p),
  post: (p, b) => request("POST", p, b || {}),
  put: (p, b) => request("PUT", p, b),
  del: (p) => request("DELETE", p),
  upload: (p, form) => request("POST", p, form, true),
  download: async (p, filename) => {
    const res = await fetch(BASE + p, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) throw new Error("Download failed");
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  },
};
