const BASE = "http://127.0.0.1:8765";

async function request(path, options = {}) {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...options.headers },
      ...options,
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`API ${res.status}: ${body}`);
    }
    return await res.json();
  } catch (err) {
    console.error(`[api] ${path} failed:`, err);
    throw err;
  }
}

export async function getStatus() {
  return request("/api/status");
}

export async function getHistory(params = {}) {
  const filtered = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== ''),
  );
  const qs = new URLSearchParams(filtered).toString();
  const path = qs ? `/api/history?${qs}` : "/api/history";
  return request(path);
}

export async function getToday() {
  return request("/api/today");
}

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch(`${BASE}/api/upload`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Upload ${res.status}: ${body}`);
    }
    return await res.json();
  } catch (err) {
    console.error("[api] upload failed:", err);
    throw err;
  }
}

export async function togglePause() {
  return request("/api/pause", { method: "POST" });
}

export async function getConfig() {
  return request("/api/config");
}

export async function getInputsStatus() {
  return request("/api/inputs");
}

export async function getSystemInfo() {
  return request("/api/system");
}
