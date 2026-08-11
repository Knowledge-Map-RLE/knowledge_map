const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

import { getToken } from '../token';

const withBase = (path: string) => {
  if (!API_BASE_URL) {
    return path;
  }
  return path.startsWith('/') ? `${API_BASE_URL}${path}` : `${API_BASE_URL}/${path}`;
};

/** Заголовки авторизации (Bearer-токен), если пользователь вошёл. */
export function authHeaders(headersInit?: HeadersInit): HeadersInit {
  const headers = new Headers(headersInit);
  const token = getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return headers;
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(authHeaders(init?.headers));
  if (init?.body && typeof init.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const merged: RequestInit = {
    ...init,
    headers,
  };
  const response = await fetch(withBase(path), merged);
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