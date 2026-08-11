import { useCallback, useEffect, useState } from 'react';
import { MdGroups, MdChatBubbleOutline } from 'react-icons/md';
import {
    createCommunity,
    getCommunity,
    joinCommunity,
    leaveCommunity,
    listCommunities,
    type Community,
    type CommunitySummary,
} from '../../../services/api/social';
import { useRequireAuth } from '../../../shared/hooks/useRequireAuth';
import { useToast } from '../../../shared/ui/Toast';
import type { ChatTarget } from '../model';
import s from '../Social_network.module.css';

interface CommunitiesPanelProps {
    onOpenChat: (target: ChatTarget) => void;
}

export function CommunitiesPanel({ onOpenChat }: CommunitiesPanelProps) {
    const requireAuth = useRequireAuth();
    const { error: toastError, success: toastSuccess } = useToast();
    const [communities, setCommunities] = useState<CommunitySummary[]>([]);
    const [expanded, setExpanded] = useState<string | null>(null);
    const [members, setMembers] = useState<Community | null>(null);
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [loading, setLoading] = useState(false);
    const [creating, setCreating] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const res = await listCommunities();
            setCommunities(res.communities ?? []);
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки сообществ');
        } finally {
            setLoading(false);
        }
    }, [toastError]);

    useEffect(() => {
        load();
    }, [load]);

    const handleCreate = async () => {
        const trimmed = name.trim();
        if (!trimmed) return;
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы создавать сообщества')) return;
        setCreating(true);
        try {
            const res = await createCommunity({ name: trimmed, description: description.trim() });
            if (res.success) {
                toastSuccess('Сообщество создано');
                setName('');
                setDescription('');
                await load();
            } else {
                toastError(res.error || 'Ошибка создания');
            }
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка создания');
        } finally {
            setCreating(false);
        }
    };

    const toggleExpand = async (uid: string) => {
        if (expanded === uid) {
            setExpanded(null);
            setMembers(null);
            return;
        }
        try {
            const res = await getCommunity(uid);
            setMembers(res.community ?? null);
            setExpanded(uid);
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки сообщества');
        }
    };

    const handleJoin = async (uid: string) => {
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы вступать в сообщества')) return;
        try {
            const res = await joinCommunity(uid);
            if (res.success) {
                toastSuccess('Вы в сообществе');
                await load();
                if (expanded === uid) await toggleExpand(uid);
            } else {
                toastError(res.error || 'Ошибка вступления');
            }
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка');
        }
    };

    const handleLeave = async (uid: string) => {
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы покидать сообщества')) return;
        try {
            await leaveCommunity(uid);
            toastSuccess('Вы покинули сообщество');
            await load();
            if (expanded === uid) await toggleExpand(uid);
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка');
        }
    };

    return (
        <div className={s.panel}>
            <div className={s.panelSection}>
                <div className={s.panelTitle}>Создать сообщество</div>
                <div className={s.row}>
                    <input
                        className={s.input}
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Название"
                    />
                </div>
                <div className={s.row}>
                    <input
                        className={s.input}
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="Описание (необязательно)"
                    />
                    <button className={s.primaryBtn} onClick={handleCreate} disabled={creating || !name.trim()}>
                        {creating ? '…' : 'Создать'}
                    </button>
                </div>
            </div>

            <div className={s.panelSection}>
                <div className={s.panelTitle}>Сообщества ({communities.length})</div>
                {loading && <div className={s.hint}>Загрузка…</div>}
                {!loading && communities.length === 0 && <div className={s.hint}>Сообществ пока нет</div>}
                {communities.map((c) => (
                    <div key={c.uid} className={s.card}>
                        <div className={s.cardRow}>
                            <div className={s.cardMain}>
                                <div className={s.cardName}>{c.name}</div>
                                <div className={s.cardSub}>{c.description || '—'}</div>
                                <div className={s.cardSub}><MdGroups /> {c.member_count}</div>
                            </div>
                            <button className={s.ghostBtn} onClick={() => onOpenChat({ type: 'community', uid: c.uid, label: c.name })}>
                                <MdChatBubbleOutline /> Обсуждение
                            </button>
                            <button className={s.ghostBtn} onClick={() => toggleExpand(c.uid)}>
                                {expanded === c.uid ? 'Свернуть' : 'Участники'}
                            </button>
                            <button className={s.primaryBtn} onClick={() => handleJoin(c.uid)}>Вступить</button>
                            <button className={s.dangerBtn} onClick={() => handleLeave(c.uid)}>Покинуть</button>
                        </div>
                        {expanded === c.uid && members && (
                            <div className={s.cardExpand}>
                                {members.members.length === 0 && <div className={s.hint}>Нет участников</div>}
                                {members.members.map((m) => (
                                    <div key={m.uid} className={s.cardRow}>
                                        <div className={s.cardMain}>
                                            <div className={s.cardName}>{m.nickname || m.login}</div>
                                            <div className={s.cardSub}>@{m.login}</div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
