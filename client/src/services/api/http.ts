const API_BASE_URL = ((import.meta as any).env?.VITE_API_BASE_URL || '').replace(/\/$/, '');

const withBase = (path: string) => {
  if (!API_BASE_URL) {
    return path;
  }
  return path.startsWith('/') ? `${API_BASE_URL}${path}` : `${API_BASE_URL}/${path}`;
};

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(withBase(path), init);
  if (!response.ok) {
    const errorBody = await response.text().catch(() => '');
    let detail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errorJson = JSON.parse(errorBody);
      detail = errorJson.detail || errorJson.message || detail;
    } catch {
      if (errorBody) detail = errorBody.slice(0, 500);
    }
    throw new Error(detail);
  }
  const cloned = response.clone();
  try {
    return await response.json() as T;
  } catch {
    const bodyPreview = await cloned.text().catch(() => '');
    throw new Error(`Failed to parse JSON from ${path}: ${bodyPreview.slice(0, 200)}`);
  }
}

export { API_BASE_URL, withBase };