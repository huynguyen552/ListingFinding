export let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET")
    headers.set("X-CSRF-Token", csrf);
  const res = await fetch("/api/v1" + path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!res.ok) {
    const body = await res
      .json()
      .catch(() => ({ message: "Không kết nối được máy chủ." }));
    if (res.status === 401 && !path.includes("/auth/login"))
      window.dispatchEvent(new Event("session-expired"));
    throw new Error(body.message || "Có lỗi xử lý.");
  }
  return res.json();
}
