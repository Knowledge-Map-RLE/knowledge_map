import type { ChatTargetType } from '../../services/api/social';
import type { IconType } from 'react-icons';
import { MdPerson, MdForum, MdHandshake, MdGroups, MdLocalFireDepartment } from 'react-icons/md';

export type SocialTabId = 'profile' | 'chat' | 'friends' | 'communities' | 'trends';

export interface ChatTarget {
    type: ChatTargetType;
    uid: string;
    label: string;
}

export const TARGET_TYPE_LABELS: Record<ChatTargetType, string> = {
    article: 'Статья',
    statement: 'Триплет',
    user: 'Пользователь',
    community: 'Сообщество',
};

export const TABS: Array<{ id: SocialTabId; label: string; icon: IconType }> = [
    { id: 'profile', label: 'Профиль', icon: MdPerson },
    { id: 'chat', label: 'Обсуждения', icon: MdForum },
    { id: 'friends', label: 'Друзья', icon: MdHandshake },
    { id: 'communities', label: 'Сообщества', icon: MdGroups },
    { id: 'trends', label: 'Тренды', icon: MdLocalFireDepartment },
];

export function formatTime(ts: number): string {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    const now = Date.now();
    const sameDay = new Date(now).toDateString() === d.toDateString();
    const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    if (sameDay) return time;
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }) + ' ' + time;
}
