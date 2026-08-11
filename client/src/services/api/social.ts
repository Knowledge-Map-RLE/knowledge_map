import { fetchJson } from './http';

/** Событие, уведомляющее UI о том, что профиль текущего пользователя изменён.
 *  Обработчики (панель профиля, аватар в шапке) перечитывают свои данные. */
export const PROFILE_UPDATED_EVENT = 'km:profile-updated';

/** Событие запроса на открытие модального окна «Личный кабинет».
 *  Испускается из любого места UI (например, из панели «Профиль»). */
export const ACCOUNT_MODAL_EVENT = 'km:open-account-modal';

// ── Типы социальной сети ───────────────────────────────────────────────────

export interface SocialContacts {
    email?: string;
    telegram?: string;
    phone?: string;
    website?: string;
}

export interface SocialUserProfile {
    uid: string;
    login: string;
    nickname: string;
    bio?: string;
    avatar_key?: string;
    contacts?: SocialContacts;
    friend_count?: number;
    communities?: CommunitySummary[];
    is_friend?: boolean;
    contributions?: { article_count: number; block_count: number };
}

export interface CommunitySummary {
    uid: string;
    name: string;
    description: string;
    member_count: number;
    created_by_uid?: string;
    is_member?: boolean;
}

export interface Community extends CommunitySummary {
    members: SocialUserProfile[];
    is_member?: boolean;
    is_owner?: boolean;
}

export type ChatTargetType = 'article' | 'statement' | 'user' | 'community';

export interface ChatReference {
    uid: string;
    type: 'block' | 'article' | 'statement';
    label: string;
    block_type?: number;
    order?: number;
}

export interface ChatMessage {
    uid: string;
    target_type: ChatTargetType;
    target_uid: string;
    author_uid: string;
    author_nickname: string;
    author_login: string;
    text: string;
    parent_uid: string;
    like_count: number;
    reply_count: number;
    liked_by_me: boolean;
    created_at: number;
    references?: ChatReference[];
}

export interface ChatThread {
    success: boolean;
    messages: ChatMessage[];
    total: number;
}

// ── Стена профиля ───────────────────────────────────────────────────────────

export interface WallComment {
    uid: string;
    post_uid: string;
    author_uid: string;
    author_nickname: string;
    author_login: string;
    text: string;
    created_at: number;
}

export interface WallPost {
    uid: string;
    owner_uid: string;
    text: string;
    created_at: number;
    comment_count: number;
    comments: WallComment[];
}

export interface WallResponse {
    success: boolean;
    posts: WallPost[];
    total: number;
}

export async function getWall(uid: string): Promise<WallResponse> {
    return fetchJson(`/api/social/wall/${encodeURIComponent(uid)}`, { method: 'GET' });
}

export async function createWallPost(
    uid: string,
    text: string,
): Promise<{ success: boolean; post?: WallPost; error?: string }> {
    return fetchJson(`/api/social/wall/${encodeURIComponent(uid)}`, {
        method: 'POST',
        body: JSON.stringify({ text }),
    });
}

export async function addWallComment(
    postUid: string,
    text: string,
): Promise<{ success: boolean; comment?: WallComment; error?: string }> {
    return fetchJson(`/api/social/wall/posts/${encodeURIComponent(postUid)}/comments`, {
        method: 'POST',
        body: JSON.stringify({ text }),
    });
}

export interface NotificationItem {
    uid: string;
    type: string;
    target_type: string;
    target_uid: string;
    text: string;
    is_read: boolean;
    created_at: number;
}

export interface NotificationsResponse {
    success: boolean;
    notifications: NotificationItem[];
    unread_count: number;
}

export interface TrendItem {
    target_type: ChatTargetType;
    target_uid: string;
    label: string;
    count: number;
}

export interface TrendsResponse {
    success: boolean;
    by_comments: TrendItem[];
    by_likes: TrendItem[];
}

export interface SocialGraphNode {
    id: string;
    type: 'user' | 'community';
    label: string;
    login?: string;
    description?: string;
    avatar_key?: string;
    friend_count?: number;
    member_count?: number;
    is_me?: boolean;
    is_friend?: boolean;
    is_member?: boolean;
}

export interface SocialGraphEdge {
    source: string;
    target: string;
    type: 'friend' | 'member';
}

export interface SocialGraph {
    success: boolean;
    nodes: SocialGraphNode[];
    edges: SocialGraphEdge[];
}

export interface MeResponse {
    success: boolean;
    profile: SocialUserProfile;
    friends: SocialUserProfile[];
    communities: CommunitySummary[];
    notifications: NotificationItem[];
    unread_count: number;
}

// ── Профиль / me ────────────────────────────────────────────────────────────

export async function getMe(): Promise<MeResponse> {
    return fetchJson<MeResponse>('/api/social/me', { method: 'GET' });
}

export async function updateProfile(body: { bio?: string; avatar_key?: string; contacts?: SocialContacts }): Promise<{
    success: boolean;
    profile?: SocialUserProfile;
    error?: string;
}> {
    return fetchJson('/api/social/profile', { method: 'PUT', body: JSON.stringify(body) });
}

// ── Пользователи / друзья ───────────────────────────────────────────────────

export async function searchUsers(q: string, limit = 20): Promise<{ success: boolean; users: SocialUserProfile[] }> {
    const params = new URLSearchParams({ q, limit: String(limit) });
    return fetchJson(`/api/social/users/search?${params.toString()}`, { method: 'GET' });
}

export async function getUserProfile(uid: string): Promise<{ success: boolean; profile?: SocialUserProfile }> {
    return fetchJson(`/api/social/users/${encodeURIComponent(uid)}/profile`, { method: 'GET' });
}

export async function listFriends(): Promise<{ success: boolean; friends: SocialUserProfile[] }> {
    return fetchJson('/api/social/friends', { method: 'GET' });
}

export async function addFriend(uid: string): Promise<{ success: boolean; is_friend?: boolean; error?: string }> {
    return fetchJson(`/api/social/friends/${encodeURIComponent(uid)}`, { method: 'POST' });
}

export async function removeFriend(uid: string): Promise<{ success: boolean; is_friend?: boolean }> {
    return fetchJson(`/api/social/friends/${encodeURIComponent(uid)}`, { method: 'DELETE' });
}

// ── Сообщества ──────────────────────────────────────────────────────────────

export async function createCommunity(body: {
    name: string;
    description?: string;
}): Promise<{ success: boolean; community?: CommunitySummary; error?: string }> {
    return fetchJson('/api/social/communities', { method: 'POST', body: JSON.stringify(body) });
}

export async function listCommunities(limit = 100): Promise<{ success: boolean; communities: CommunitySummary[] }> {
    return fetchJson(`/api/social/communities?limit=${limit}`, { method: 'GET' });
}

export async function searchCommunities(q: string, limit = 20): Promise<{
    success: boolean;
    communities: CommunitySummary[];
}> {
    const params = new URLSearchParams({ q, limit: String(limit) });
    return fetchJson(`/api/social/communities/search?${params.toString()}`, { method: 'GET' });
}

export async function getMyCommunities(): Promise<{
    success: boolean;
    communities: CommunitySummary[];
}> {
    return fetchJson('/api/social/communities/mine', { method: 'GET' });
}

export async function getCommunity(uid: string): Promise<{ success: boolean; community?: Community }> {
    return fetchJson(`/api/social/communities/${encodeURIComponent(uid)}`, { method: 'GET' });
}

export async function joinCommunity(uid: string): Promise<{ success: boolean; is_member?: boolean; error?: string }> {
    return fetchJson(`/api/social/communities/${encodeURIComponent(uid)}/join`, { method: 'POST' });
}

export async function leaveCommunity(uid: string): Promise<{ success: boolean; is_member?: boolean }> {
    return fetchJson(`/api/social/communities/${encodeURIComponent(uid)}/leave`, { method: 'POST' });
}

// ── Чат ─────────────────────────────────────────────────────────────────────

export async function getChat(
    targetType: ChatTargetType,
    targetUid: string,
    before?: number,
    limit = 50,
): Promise<ChatThread> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (before) params.set('before', String(before));
    return fetchJson(
        `/api/social/chat/${targetType}/${encodeURIComponent(targetUid)}?${params.toString()}`,
        { method: 'GET' },
    );
}

export async function sendMessage(
    targetType: ChatTargetType,
    targetUid: string,
    text: string,
    parentUid?: string,
    references?: { uid: string; type: 'block' | 'article' | 'statement' }[],
): Promise<{ success: boolean; message?: ChatMessage; error?: string }> {
    return fetchJson(`/api/social/chat/${targetType}/${encodeURIComponent(targetUid)}`, {
        method: 'POST',
        body: JSON.stringify({
            text,
            parent_uid: parentUid ?? null,
            references: references && references.length ? references : null,
        }),
    });
}

export async function toggleLike(messageUid: string): Promise<{
    success: boolean;
    liked?: boolean;
    like_count?: number;
    error?: string;
}> {
    return fetchJson(`/api/social/chat/messages/${encodeURIComponent(messageUid)}/like`, { method: 'POST' });
}

// ── Контакты (обфускация) ───────────────────────────────────────────────────

/**
 * Сервер отдаёт контакты в base64, чтобы массовые краулеры не могли собрать
 * их простым парсингом JSON/HTML. Расшифровка выполняется в браузере перед
 * отрисовкой.
 */
export function decodeContacts(contacts?: SocialContacts): SocialContacts {
    if (!contacts) return {};
    const decoded: SocialContacts = {};
    for (const [key, value] of Object.entries(contacts)) {
        if (!value) continue;
        let text = value;
        try {
            const binary = atob(value);
            const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0));
            text = new TextDecoder('utf-8').decode(bytes);
        } catch {
            // не base64 — оставляем как есть (устаревшие данные)
        }
        decoded[key as keyof SocialContacts] = text;
    }
    return decoded;
}

// ── Уведомления ─────────────────────────────────────────────────────────────

export async function getNotifications(): Promise<NotificationsResponse> {
    return fetchJson('/api/social/notifications', { method: 'GET' });
}

export async function markNotificationsRead(notificationUid?: string): Promise<{ success: boolean }> {
    return fetchJson('/api/social/notifications/read', {
        method: 'POST',
        body: JSON.stringify({ notification_uid: notificationUid ?? null }),
    });
}

// ── Тренды / жалобы / граф ──────────────────────────────────────────────────

export async function getTrends(limit = 10): Promise<TrendsResponse> {
    return fetchJson(`/api/social/trends?limit=${limit}`, { method: 'GET' });
}

export async function createComplaint(body: {
    target_type: ChatTargetType;
    target_uid: string;
    reason: string;
    comment?: string;
}): Promise<{ success: boolean; complaint_uid?: string; error?: string }> {
    return fetchJson('/api/social/complaints', { method: 'POST', body: JSON.stringify(body) });
}

export async function getSocialGraph(): Promise<SocialGraph> {
    return fetchJson('/api/social/graph', { method: 'GET' });
}

export async function getGraphUser(uid: string): Promise<SocialGraph> {
    return fetchJson(`/api/social/graph/user/${encodeURIComponent(uid)}`, { method: 'GET' });
}

// ── Изображения ─────────────────────────────────────────────────────────────

export interface UploadImageResult {
    success: boolean;
    object_key?: string;
    error?: string;
}

export async function uploadImage(file: File): Promise<UploadImageResult> {
    const fd = new FormData();
    fd.append('file', file);
    return fetchJson('/api/social/images', { method: 'POST', body: fd });
}

export function socialImageUrl(objectKey: string): string {
    return `/api/social/images/${objectKey}`;
}

export async function deleteSocialImage(objectKey: string): Promise<{ success: boolean }> {
    return fetchJson(`/api/social/images/${encodeURIComponent(objectKey)}`, { method: 'DELETE' });
}

// ── Вклад / уведомления / resolve ───────────────────────────────────────────

export async function getContributions(uid: string): Promise<{
    success: boolean;
    contributions?: { article_count: number; block_count: number };
}> {
    return fetchJson(`/api/social/users/${encodeURIComponent(uid)}/contributions`, { method: 'GET' });
}

export async function getUnreadCount(): Promise<{ success: boolean; unread_count: number }> {
    return fetchJson('/api/social/notifications/unread-count', { method: 'GET' });
}

export interface ResolvedEntity {
    uid: string;
    type: 'block' | 'article' | 'statement' | 'community' | 'user' | 'message';
    label: string;
    block_type?: number;
    order?: number;
    target_type?: string;
    data?: Record<string, string | boolean | number | null>;
}

export async function resolveEntity(uid: string): Promise<{ success: boolean; entity?: ResolvedEntity }> {
    return fetchJson(`/api/social/resolve/${encodeURIComponent(uid)}`, { method: 'GET' });
}

// ── Управление сообществами ─────────────────────────────────────────────────

export async function updateCommunity(uid: string, body: {
    name?: string;
    description?: string;
}): Promise<{ success: boolean; community?: Community; error?: string }> {
    return fetchJson(`/api/social/communities/${encodeURIComponent(uid)}`, {
        method: 'PUT',
        body: JSON.stringify(body),
    });
}

export async function deleteCommunity(uid: string): Promise<{ success: boolean; error?: string }> {
    return fetchJson(`/api/social/communities/${encodeURIComponent(uid)}`, { method: 'DELETE' });
}
