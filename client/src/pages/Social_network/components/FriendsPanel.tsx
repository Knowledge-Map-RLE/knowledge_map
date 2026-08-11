import { useCallback, useEffect, useState } from 'react';
import {
    addFriend,
    listFriends,
    removeFriend,
    searchUsers,
    type SocialUserProfile,
} from '../../../services/api/social';
import { useRequireAuth } from '../../../shared/hooks/useRequireAuth';
import { useToast } from '../../../shared/ui/Toast';
import { MdChatBubbleOutline } from 'react-icons/md';
import { useAuth } from '../../../entities/auth';
import type { ChatTarget } from '../model';
import s from '../Social_network.module.css';

interface FriendsPanelProps {
    onOpenChat: (target: ChatTarget) => void;
}

export function FriendsPanel({ onOpenChat }: FriendsPanelProps) {
    const requireAuth = useRequireAuth();
    const { error: toastError, success: toastSuccess } = useToast();
    const { isAuthenticated, requestLogin } = useAuth();
    const [friends, setFriends] = useState<SocialUserProfile[]>([]);
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<SocialUserProfile[]>([]);
    const [searching, setSearching] = useState(false);
    const [loading, setLoading] = useState(false);

    const load = useCallback(async () => {
        if (!isAuthenticated) {
            setFriends([]);
            return;
        }
        setLoading(true);
        try {
            const res = await listFriends();
            setFriends(res.friends ?? []);
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки друзей');
        } finally {
            setLoading(false);
        }
    }, [isAuthenticated, toastError]);

    useEffect(() => {
        load();
    }, [load]);

    const handleSearch = async () => {
        const q = query.trim();
        if (!q) return;
        setSearching(true);
        try {
            const res = await searchUsers(q);
            setResults(res.users ?? []);
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка поиска');
        } finally {
            setSearching(false);
        }
    };

    const handleAdd = async (uid: string) => {
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы добавлять друзей')) return;
        try {
            const res = await addFriend(uid);
            if (res.success) {
                toastSuccess('В друзьях');
                await load();
                setResults((prev) => prev.map((u) => (u.uid === uid ? { ...u, is_friend: true } : u)));
            } else {
                toastError(res.error || 'Не удалось добавить');
            }
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка');
        }
    };

    const handleRemove = async (uid: string) => {
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы управлять друзьями')) return;
        if (!window.confirm('Убрать из друзей?')) return;
        try {
            await removeFriend(uid);
            toastSuccess('Удалено из друзей');
            await load();
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка');
        }
    };

    return (
        <div className={s.panel}>
            <div className={s.panelSection}>
                <div className={s.panelTitle}>Поиск пользователей</div>
                <div className={s.row}>
                    <input
                        className={s.input}
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                        placeholder="Логин или никнейм"
                    />
                    <button className={s.primaryBtn} onClick={handleSearch} disabled={searching || !query.trim()}>
                        {searching ? '…' : 'Найти'}
                    </button>
                </div>
                {results.map((u) => (
                    <div key={u.uid} className={s.cardRow}>
                        <div className={s.cardMain}>
                            <div className={s.cardName}>{u.nickname || u.login}</div>
                            <div className={s.cardSub}>@{u.login}</div>
                        </div>
                        <button className={s.ghostBtn} onClick={() => onOpenChat({ type: 'user', uid: u.uid, label: u.nickname || u.login })}>
                            <MdChatBubbleOutline />
                        </button>
                        {u.is_friend || friends.some((f) => f.uid === u.uid) ? (
                            <button className={s.dangerBtn} onClick={() => handleRemove(u.uid)}>Убрать</button>
                        ) : (
                            <button className={s.primaryBtn} onClick={() => handleAdd(u.uid)}>Добавить</button>
                        )}
                    </div>
                ))}
            </div>

            <div className={s.panelSection}>
                <div className={s.panelTitle}>Мои друзья ({friends.length})</div>
                {!isAuthenticated && (
                    <div className={s.gateCard}>
                        <div className={s.gateText}>
                            Войдите или зарегистрируйтесь, чтобы видеть своих друзей.
                        </div>
                        <button className={s.primaryBtn} onClick={requestLogin}>Войти / Зарегистрироваться</button>
                    </div>
                )}
                {isAuthenticated && loading && <div className={s.hint}>Загрузка…</div>}
                {isAuthenticated && !loading && friends.length === 0 && <div className={s.hint}>Друзей пока нет</div>}
                {friends.map((f) => (
                    <div key={f.uid} className={s.cardRow}>
                        <div className={s.cardMain}>
                            <div className={s.cardName}>{f.nickname || f.login}</div>
                            <div className={s.cardSub}>@{f.login}</div>
                        </div>
                        <button className={s.ghostBtn} onClick={() => onOpenChat({ type: 'user', uid: f.uid, label: f.nickname || f.login })}>
                            <MdChatBubbleOutline /> Написать
                        </button>
                        <button className={s.dangerBtn} onClick={() => handleRemove(f.uid)}>Убрать</button>
                    </div>
                ))}
            </div>
        </div>
    );
}
