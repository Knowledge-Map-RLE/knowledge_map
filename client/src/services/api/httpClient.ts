const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

const withBase = (path: string) => {
  if (!API_BASE_URL) {
    return path;
  }
  return path.startsWith('/') ? `${API_BASE_URL}${path}` : `${API_BASE_URL}/${path}`;
};

import { getToken } from '../token';
import { getSessionId } from '../telemetry';

class HttpClient {
  async request(method: string, path: string, body?: unknown): Promise<Response> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    
    const token = getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const sessionId = getSessionId();
    if (sessionId) {
      headers['X-Client-Session-ID'] = sessionId;
    }

    const res = await fetch(withBase(path), {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    return res;
  }

  async get(path: string): Promise<Response> {
    return this.request('GET', path);
  }

  async post(path: string, body?: unknown): Promise<Response> {
    return this.request('POST', path, body);
  }

  async put(path: string, body?: unknown): Promise<Response> {
    return this.request('PUT', path, body);
  }

  async delete(path: string): Promise<Response> {
    return this.request('DELETE', path);
  }
}

export const httpClient = new HttpClient();

export { API_BASE_URL, withBase };