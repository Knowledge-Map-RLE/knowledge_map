import { useCallback, useEffect, useMemo, useState } from 'react';
import {
    acceptFriend,
    addFriend,
    cancelFriendRequest,
    declineFriend,
    getFriendRequests,
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
    const [requestsIncoming, setRequestsIncoming] = useState<SocialUserProfile[]>([]);
    const [requestsOutgoing, setRequestsOutgoing] = useState<SocialUserProfile[]>([]);
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<SocialUserProfile[]>([]);
    const [searching, setSearching] = useState(false);
    const [loading, setLoading] = useState(false);

    const load = useCallback(async () => {
        if (!isAuthenticated) {
            setFriends([]);
            setRequestsIncoming([]);
            setRequestsOutgoing([]);
            return;
        }
        setLoading(true);
        try {
            const res = await listFriends();
            setFriends(res.friends ?? []);
            const reqs = await getFriendRequests();
            setRequestsIncoming(reqs.incoming ?? []);
            setRequestsOutgoing(reqs.outgoing ?? []);
            window.dispatchEvent(new Event('social:graph-refresh'));
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

    const handleSendRequest = async (uid: string) => {
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы добавлять друзей')) return;
        try {
            const res = await addFriend(uid);
            if (res.success) {
                toastSuccess(res.status === 'requested' ? 'Заявка отправлена' : 'Вы уже в друзьях');
                await load();
            } else {
                toastError(res.error || 'Не удалось отправить заявку');
            }
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка');
        }
    };

    const handleAccept = async (uid: string) => {
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы управлять заявками')) return;
        try {
            await acceptFriend(uid);
            toastSuccess('Заявка принята — вы в друзьях');
            await load();
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка');
        }
    };

    const handleDecline = async (uid: string) => {
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы управлять заявками')) return;
        try {
            await declineFriend(uid);
            toastSuccess('Заявка отклонена');
            await load();
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка');
        }
    };

    const handleCancelRequest = async (uid: string) => {
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы управлять заявками')) return;
        try {
            await cancelFriendRequest(uid);
            toastSuccess('Заявка отменена');
            await load();
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

    const friendUids = useMemo(() => new Set(friends.map((f) => f.uid)), [friends]);
    const outgoingUids = useMemo(() => new Set(requestsOutgoing.map((u) => u.uid)), [requestsOutgoing]);
    const incomingUids = useMemo(() => new Set(requestsIncoming.map((u) => u.uid)), [requestsIncoming]);

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
                        {friendUids.has(u.uid) ? (
                            <button className={s.dangerBtn} onClick={() => handleRemove(u.uid)}>Убрать</button>
                        ) : outgoingUids.has(u.uid) ? (
                            <button className={s.ghostBtn} onClick={() => handleCancelRequest(u.uid)}>Отменить заявку</button>
                        ) : incomingUids.has(u.uid) ? (
                            <button className={s.primaryBtn} onClick={() => handleAccept(u.uid)}>Принять заявку</button>
                        ) : (
                            <button className={s.primaryBtn} onClick={() => handleSendRequest(u.uid)}>Добавить</button>
                        )}
                    </div>
                ))}
            </div>

            {isAuthenticated && (
                <div className={s.panelSection}>
                    <div className={s.panelTitle}>Входящие заявки ({requestsIncoming.length})</div>
                    {loading && <div className={s.hint}>Загрузка…</div>}
                    {!loading && requestsIncoming.length === 0 && <div className={s.hint}>Входящих заявок нет</div>}
                    {requestsIncoming.map((f) => (
                        <div key={f.uid} className={s.cardRow}>
                            <div className={s.cardMain}>
                                <div className={s.cardName}>{f.nickname || f.login}</div>
                                <div className={s.cardSub}>@{f.login}</div>
                            </div>
                            <button className={s.primaryBtn} onClick={() => handleAccept(f.uid)}>Принять</button>
                            <button className={s.dangerBtn} onClick={() => handleDecline(f.uid)}>Отклонить</button>
                        </div>
                    ))}
                </div>
            )}

            {isAuthenticated && (
                <div className={s.panelSection}>
                    <div className={s.panelTitle}>Исходящие заявки ({requestsOutgoing.length})</div>
                    {loading && <div className={s.hint}>Загрузка…</div>}
                    {!loading && requestsOutgoing.length === 0 && <div className={s.hint}>Исходящих заявок нет</div>}
                    {requestsOutgoing.map((f) => (
                        <div key={f.uid} className={s.cardRow}>
                            <div className={s.cardMain}>
                                <div className={s.cardName}>{f.nickname || f.login}</div>
                                <div className={s.cardSub}>@{f.login}</div>
                            </div>
                            <button className={s.ghostBtn} onClick={() => handleCancelRequest(f.uid)}>Отменить</button>
                        </div>
                    ))}
                </div>
            )}

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
