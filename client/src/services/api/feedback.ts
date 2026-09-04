import { fetchJson, authHeaders } from './http';
import type { BrowserInfo } from '../../shared/utils/browserInfo';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export type FeedbackStatus = 'new' | 'in_development' | 'resolved' | 'rejected';

export const STATUS_COLORS: Record<FeedbackStatus, string> = {
    new: '#3B82F6',
    in_development: '#F97316',
    resolved: '#22C55E',
    rejected: '#1F2937',
};

export const STATUS_LABELS: Record<FeedbackStatus, string> = {
    new: 'Новое',
    in_development: 'В разработке',
    resolved: 'Решено',
    rejected: 'Отклонено',
};

export interface FeedbackTicket {
    uid: string;
    user_uid: string;
    status: FeedbackStatus;
    browser_info?: Record<string, unknown>;
    app_version?: string;
    created_at: number;
    updated_at: number;
}

export interface FeedbackMessage {
    uid: string;
    sender_uid: string;
    sender_type: 'user' | 'admin';
    text: string;
    image_s3_keys: string[];
    created_at: number;
}

export interface FeedbackDraft {
    text: string;
    updated_at: number;
}

// ── Tickets ─────────────────────────────────────────────────────────────

export async function createTicket(
    text: string,
    browserInfo: BrowserInfo,
    appVersion: string,
    imageKeys: string[] = [],
): Promise<{ success: boolean; ticket: { uid: string; status: string; created_at: number } }> {
    const formData = new FormData();
    formData.append('text', text);
    formData.append('browser_info_json', JSON.stringify(browserInfo));
    formData.append('app_version', appVersion);
    formData.append('image_keys_json', JSON.stringify(imageKeys));

    const response = await fetch(`${API_BASE}/api/feedback/tickets`, {
        method: 'POST',
        headers: authHeaders(),
        body: formData,
    });

    if (!response.ok) {
        const body = await response.text();
        let detail = `HTTP ${response.status}`;
        try {
            detail = JSON.parse(body).detail || detail;
        } catch {
            if (body) detail = body.slice(0, 300);
        }
        throw new Error(detail);
    }

    return response.json();
}

export async function listFeedbackTickets(params?: {
    status?: string;
    user_uid?: string;
    limit?: number;
    offset?: number;
}): Promise<{ tickets: FeedbackTicket[]; total: number }> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.user_uid) qs.set('user_uid', params.user_uid);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return fetchJson(`/api/feedback/tickets${query ? `?${query}` : ''}`);
}

export async function getFeedbackTicket(
    ticketUid: string,
): Promise<{ ticket: FeedbackTicket; messages: FeedbackMessage[] }> {
    return fetchJson(`/api/feedback/tickets/${ticketUid}`);
}

export async function updateTicketStatus(
    ticketUid: string,
    status: FeedbackStatus,
): Promise<{ success: boolean; ticket: { uid: string; status: string; updated_at: number } }> {
    const formData = new FormData();
    formData.append('status', status);

    const response = await fetch(`${API_BASE}/api/feedback/tickets/${ticketUid}/status`, {
        method: 'PATCH',
        headers: authHeaders(),
        body: formData,
    });

    if (!response.ok) {
        const body = await response.text();
        let detail = `HTTP ${response.status}`;
        try {
            detail = JSON.parse(body).detail || detail;
        } catch {
            if (body) detail = body.slice(0, 300);
        }
        throw new Error(detail);
    }

    return response.json();
}

// ── Messages ────────────────────────────────────────────────────────────

export async function sendFeedbackMessage(
    ticketUid: string,
    text: string,
    imageKeys: string[] = [],
    senderType: 'user' | 'admin' = 'user',
): Promise<{ success: boolean; message: FeedbackMessage }> {
    const formData = new FormData();
    formData.append('text', text);
    formData.append('image_keys_json', JSON.stringify(imageKeys));
    formData.append('sender_type', senderType);

    const response = await fetch(`${API_BASE}/api/feedback/tickets/${ticketUid}/messages`, {
        method: 'POST',
        headers: authHeaders(),
        body: formData,
    });

    if (!response.ok) {
        const body = await response.text();
        let detail = `HTTP ${response.status}`;
        try {
            detail = JSON.parse(body).detail || detail;
        } catch {
            if (body) detail = body.slice(0, 300);
        }
        throw new Error(detail);
    }

    return response.json();
}

export async function getFeedbackMessages(
    ticketUid: string,
): Promise<{ messages: FeedbackMessage[] }> {
    return fetchJson(`/api/feedback/tickets/${ticketUid}/messages`);
}

// ── Drafts ──────────────────────────────────────────────────────────────

export async function saveDraft(text: string): Promise<{ success: boolean; draft: FeedbackDraft }> {
    const formData = new FormData();
    formData.append('text', text);

    const response = await fetch(`${API_BASE}/api/feedback/drafts`, {
        method: 'PUT',
        headers: authHeaders(),
        body: formData,
    });

    if (!response.ok) {
        const body = await response.text();
        let detail = `HTTP ${response.status}`;
        try {
            detail = JSON.parse(body).detail || detail;
        } catch {
            if (body) detail = body.slice(0, 300);
        }
        throw new Error(detail);
    }

    return response.json();
}

export async function getDraft(): Promise<{ draft: FeedbackDraft }> {
    return fetchJson('/api/feedback/drafts');
}

export async function deleteDraft(): Promise<{ success: boolean }> {
    const response = await fetch(`${API_BASE}/api/feedback/drafts`, {
        method: 'DELETE',
        headers: authHeaders(),
    });

    if (!response.ok) {
        const body = await response.text();
        let detail = `HTTP ${response.status}`;
        try {
            detail = JSON.parse(body).detail || detail;
        } catch {
            if (body) detail = body.slice(0, 300);
        }
        throw new Error(detail);
    }

    return response.json();
}

export function feedbackImageUrl(objectKey: string): string {
    return `/api/feedback/images/${objectKey}`;
}

// ── Upload ──────────────────────────────────────────────────────────────

export async function uploadFeedbackImage(
    file: File,
): Promise<{ success: boolean; s3_key: string }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/api/feedback/uploads`, {
        method: 'POST',
        headers: authHeaders(),
        body: formData,
    });

    if (!response.ok) {
        const body = await response.text();
        let detail = `HTTP ${response.status}`;
        try {
            detail = JSON.parse(body).detail || detail;
        } catch {
            if (body) detail = body.slice(0, 300);
        }
        throw new Error(detail);
    }

    return response.json();
}
