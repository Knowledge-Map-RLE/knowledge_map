import { fetchJson } from './http';

export type UserRole = 'admin' | 'user';

export interface UserMeResponse {
    success: boolean;
    uid: string;
    login: string;
    nickname: string;
    role: UserRole;
}

/** Данные текущего пользователя по версии api-сервиса (включая роль). */
export async function fetchUserMe(): Promise<UserMeResponse> {
    return fetchJson<UserMeResponse>('/api/user/me');
}
