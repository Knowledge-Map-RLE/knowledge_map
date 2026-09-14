import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
    MdArrowBack, MdPerson, MdEmail, MdSend, MdCall, MdLanguage, MdGroups, MdAccountBalance,
} from 'react-icons/md';
import Header from '../../widgets/Header';
import {
    acceptFriend,
    addFriend,
    cancelFriendRequest,
    decodeContacts,
    getCommunity,
    getUserProfile,
    joinCommunity,
    leaveCommunity,
    listUserFriends,
    removeFriend,
    socialImageUrl,
    type Community,
    type PublicFriend,
    type SocialUserProfile,
} from '../../services/api/social';
import { useAuth } from '../../entities/auth';
import { useRequireAuth } from '../../shared/hooks/useRequireAuth';
import { useToast } from '../../shared/ui/Toast';
import { Wall } from './components/Wall';
import s from './Social_network.module.css';

interface UserProfileData {
    kind: 'user';
    profile: SocialUserProfile;
    friend_count: number;
    communities: Array<{ uid: string; name: string; description: string }>;
    contributions?: { article_count: number; block_count: number };
    is_friend?: boolean;
    friend_state?: 'friends' | 'outgoing' | 'incoming' | 'none';
    is_me?: boolean;
}

interface CommunityProfileData {
    kind: 'community';
    community: Community;
    is_member?: boolean;
}

type ProfileData = UserProfileData | CommunityProfileData | null;

export default function ProfilePage() {
    const { uid } = useParams<{ uid: string }>();
    const { user } = useAuth();
    const requireAuth = useRequireAuth();
    const navigate = useNavigate();
    const toast = useToast();
    const [data, setData] = useState<ProfileData>(null);
    const [loading, setLoading] = useState(true);
    const [actionBusy, setActionBusy] = useState(false);

    const myUid = user?.uid ?? '';

    const load = useCallback(async () => {
        if (!uid) return;
        setLoading(true);
        try {
            const ures = await getUserProfile(uid);
            if (ures.success && ures.profile) {
                const p = ures.profile;
                setData({
                    kind: 'user',
                    profile: p,
                    friend_count: p.friend_count ?? 0,
                    communities: p.communities ?? [],
                    contributions: p.contributions,
                    is_friend: p.is_friend,
                    friend_state: p.friend_state ?? 'none',
                    is_me: p.uid === myUid,
                });
                return;
            }
            const cres = await getCommunity(uid);
            if (cres.success && cres.community) {
                setData({ kind: 'community', community: cres.community, is_member: cres.community.is_member });
                return;
            }
            setData(null);
            toast.error('Профиль не найден');
        } catch (e) {
            toast.error(e instanceof Error ? e.message : 'Ошибка загрузки профиля');
            setData(null);
        } finally {
            setLoading(false);
        }
    }, [uid, myUid, toast]);

    useEffect(() => {
        load();
    }, [load]);

    const toggleFriend = async () => {
        if (!data || data.kind !== 'user' || !uid) return;
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы добавлять друзей')) return;
        const state = data.friend_state ?? 'none';
        setActionBusy(true);
        try {
            if (state === 'friends') {
                await removeFriend(uid);
                toast.success('Удалено из друзей');
            } else if (state === 'outgoing') {
                await cancelFriendRequest(uid);
                toast.success('Заявка отменена');
            } else if (state === 'incoming') {
                await acceptFriend(uid);
                toast.success('Заявка принята — вы в друзьях');
            } else {
                await addFriend(uid);
                toast.success('Заявка отправлена');
            }
            await load();
        } catch (e) {
            toast.error(e instanceof Error ? e.message : 'Ошибка изменения дружбы');
        } finally {
            setActionBusy(false);
        }
    };

    const toggleJoin = async () => {
        if (!data || data.kind !== 'community' || !uid) return;
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы вступать в сообщества')) return;
        setActionBusy(true);
        try {
            if (data.is_member) {
                await leaveCommunity(uid);
                toast.success('Вы покинули сообщество');
            } else {
                await joinCommunity(uid);
                toast.success('Вы вступили в сообщество');
            }
            await load();
        } catch (e) {
            toast.error(e instanceof Error ? e.message : 'Ошибка вступления');
        } finally {
            setActionBusy(false);
        }
    };

    const openChat = () => {
        if (!uid) return;
        navigate('/social_network', { state: { chat: { type: data?.kind === 'community' ? 'community' : 'user', uid, label: '' } } });
    };

    return (
        <div className={s.page}>
            <Header className={s.header} />
            <main className={s.main}>
                <div className={s.profileNav}>
                    <Link to="/social_network" className={s.ghostBtn}><MdArrowBack /> Назад к соцсети</Link>
                </div>
                {loading ? (
                    <div className={s.gateCard}>Загрузка…</div>
                ) : !data ? (
                    <div className={s.gateCard}>Профиль не найден</div>
                ) : data.kind === 'user' ? (
                    <UserProfileView
                        data={data}
                        actionBusy={actionBusy}
                        onToggleFriend={toggleFriend}
                        onOpenChat={openChat}
                    />
                ) : (
                    <CommunityProfileView
                        data={data}
                        actionBusy={actionBusy}
                        onToggleJoin={toggleJoin}
                        onOpenChat={openChat}
                    />
                )}
            </main>
        </div>
    );
}

function Avatar({ url, size = 64 }: { url?: string; size?: number }) {
    return url ? (
        <img src={socialImageUrl(url)} alt="" className={s.profileAvatar} style={{ width: size, height: size }} />
    ) : (
        <div className={s.profileAvatar} style={{ width: size, height: size }}><MdPerson /></div>
    );
}

const CONTACT_DEFS: Array<{
    key: keyof NonNullable<SocialUserProfile['contacts']>;
    icon: ReactNode;
    href?: (v: string) => string;
}> = [
    { key: 'email', icon: <MdEmail />, href: (v) => `mailto:${v}` },
    { key: 'telegram', icon: <MdSend />, href: (v) => `https://t.me/${v.replace(/^@/, '')}` },
    { key: 'phone', icon: <MdCall />, href: (v) => `tel:${v.replace(/[^\d+]/g, '')}` },
    { key: 'website', icon: <MdLanguage />, href: (v) => (v.startsWith('http://') || v.startsWith('https://') ? v : `https://${v}`) },
];

function renderContacts(contacts?: SocialUserProfile['contacts']) {
    const decoded = decodeContacts(contacts);
    const entries = Object.entries(decoded).filter(([, v]) => v && String(v).trim());
    if (entries.length === 0) return null;
    return (
        <div className={s.profileSection}>
            <div className={s.panelTitle}>Контакты</div>
            <div className={s.contactsRow}>
                {entries.map(([key, value]) => {
                    const def = CONTACT_DEFS.find((d) => d.key === key);
                    const text = String(value);
                    const href = def?.href?.(text);
                    const inner = (
                        <>
                            <span>{def?.icon ?? '•'}</span>
                            <span>{text}</span>
                        </>
                    );
                    return href ? (
                        <a key={key} className={s.contactItem} href={href} target="_blank" rel="noreferrer">
                            {inner}
                        </a>
                    ) : (
                        <span key={key} className={s.contactItem}>{inner}</span>
                    );
                })}
            </div>
        </div>
    );
}

function stepsLabel(n: number): string {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return `${n} шаг`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} шага`;
    return `${n} шагов`;
}

type ProfileTabId = 'profile' | 'wall' | 'friends';

function UserProfileView({
    data,
    actionBusy,
    onToggleFriend,
    onOpenChat,
}: {
    data: UserProfileData;
    actionBusy: boolean;
    onToggleFriend: () => void;
    onOpenChat: () => void;
}) {
    const p = data.profile;
    const [tab, setTab] = useState<ProfileTabId>('profile');
    const friendLabel =
        data.friend_state === 'friends'
            ? 'Убрать из друзей'
            : data.friend_state === 'outgoing'
                ? 'Отменить заявку'
                : data.friend_state === 'incoming'
                    ? 'Подтвердить заявку'
                    : 'Добавить в друзья';
    return (
        <div className={s.card}>
            <div className={s.profileHead}>
                <Avatar url={p.avatar_key} />
                <div className={s.profileHeadInfo}>
                    <div className={s.cardName}>{p.nickname || p.login}</div>
                    <div className={s.cardSub}>@{p.login} {data.is_me && '· это вы'}</div>
                    {p.bio && <div className={s.profileBio}>{p.bio}</div>}
                </div>
                <div className={s.profileActions}>
                    {!data.is_me && (
                        <button className={s.ghostBtn} onClick={onToggleFriend} disabled={actionBusy}>
                            {friendLabel}
                        </button>
                    )}
                    <button className={s.ghostBtn} onClick={onOpenChat}>Сообщение</button>
                </div>
            </div>
            <div className={s.statsRow}>
                <div className={s.stat}><b>{data.friend_count}</b> друзей</div>
                <div className={s.stat}><b>{data.communities.length}</b> сообществ</div>
                <div className={s.stat}><b>{data.contributions?.article_count ?? 0}</b> статей</div>
                <div className={s.stat}><b>{data.contributions?.block_count ?? 0}</b> блоков</div>
            </div>
            <nav className={s.tabs}>
                <button
                    className={tab === 'profile' ? `${s.tab} ${s.tabActive}` : s.tab}
                    onClick={() => setTab('profile')}
                >
                    Профиль
                </button>
                <button
                    className={tab === 'wall' ? `${s.tab} ${s.tabActive}` : s.tab}
                    onClick={() => setTab('wall')}
                >
                    Стена
                </button>
                <button
                    className={tab === 'friends' ? `${s.tab} ${s.tabActive}` : s.tab}
                    onClick={() => setTab('friends')}
                >
                    Друзья ({data.friend_count})
                </button>
            </nav>
            {tab === 'profile' && (
                <>
                    {renderContacts(p.contacts)}
                    {data.communities.length > 0 && (
                        <div className={s.profileSection}>
                            <div className={s.panelTitle}>Сообщества</div>
                            <div className={s.row}>
                                {data.communities.map((c) => (
                                    <Link
                                        key={c.uid}
                                        to={`/social_network/profile/${encodeURIComponent(c.uid)}`}
                                        className={s.cardRow}
                                        role="button"
                                    >
                                        <span><MdGroups /></span>
                                        <span className={s.cardMain}>
                                            <span className={s.cardName}>{c.name}</span>
                                            <span className={s.cardSub}>{c.description}</span>
                                        </span>
                                    </Link>
                                ))}
                            </div>
                        </div>
                    )}
                </>
            )}
            {tab === 'wall' && <Wall uid={p.uid} isMe={data.is_me} />}
            {tab === 'friends' && <FriendsTab uid={p.uid} selfViewed={data.is_me} />}
        </div>
    );
}

function FriendsTab({ uid, selfViewed }: { uid: string; selfViewed: boolean }) {
    const toast = useToast();
    const { isAuthenticated } = useAuth();
    const [friends, setFriends] = useState<PublicFriend[] | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        (async () => {
            try {
                const res = await listUserFriends(uid);
                if (!cancelled) setFriends(res.friends ?? []);
            } catch (e) {
                if (!cancelled) {
                    toast.error(e instanceof Error ? e.message : 'Ошибка загрузки друзей');
                    setFriends([]);
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [uid, toast]);

    return (
        <div className={s.profileSection}>
            <div className={s.panelTitle}>Друзья пользователя</div>
            {!selfViewed && (
                <div className={s.hint}>
                    Список отсортирован по близости к вам — через проверенных друзей до любого человека
                    не более 6 «рукопожатий»
                </div>
            )}
            {loading && <div className={s.hint}>Загрузка…</div>}
            {!loading && friends?.length === 0 && <div className={s.hint}>Друзей пока нет</div>}
            <div className={s.row}>
                {(friends ?? []).map((f) => {
                    const hasDistance = typeof f.distance === 'number';
                    const showFar = isAuthenticated && !selfViewed && !hasDistance;
                    return (
                        <Link
                            key={f.uid}
                            to={`/social_network/profile/${encodeURIComponent(f.uid)}`}
                            className={s.cardRow}
                            role="button"
                        >
                            <Avatar url={f.avatar_key} size={32} />
                            <span className={s.cardMain}>
                                <span className={s.cardName}>{f.nickname || f.login}</span>
                                <span className={s.cardSub}>@{f.login}</span>
                            </span>
                            {hasDistance ? (
                                <span className={s.friendBadge}>{stepsLabel(f.distance as number)}</span>
                            ) : showFar ? (
                                <span className={`${s.friendBadge} ${s.friendBadgeFar}`}>дальше 6 шагов</span>
                            ) : null}
                        </Link>
                    );
                })}
            </div>
        </div>
    );
}

function CommunityProfileView({
    data,
    actionBusy,
    onToggleJoin,
    onOpenChat,
}: {
    data: CommunityProfileData;
    actionBusy: boolean;
    onToggleJoin: () => void;
    onOpenChat: () => void;
}) {
    const c = data.community;
    return (
        <div className={s.card}>
            <div className={s.profileHead}>
                <div className={s.profileAvatar}><MdAccountBalance /></div>
                <div className={s.profileHeadInfo}>
                    <div className={s.cardName}>{c.name}</div>
                    <div className={s.cardSub}>{c.member_count} участников</div>
                    {c.description && <div className={s.profileBio}>{c.description}</div>}
                </div>
                <div className={s.profileActions}>
                    <button className={s.ghostBtn} onClick={onToggleJoin} disabled={actionBusy}>
                        {data.is_member ? 'Покинуть' : 'Вступить'}
                    </button>
                    <button className={s.ghostBtn} onClick={onOpenChat}>Обсуждение</button>
                </div>
            </div>
            {(c.members ?? []).length > 0 && (
                <div className={s.profileSection}>
                    <div className={s.panelTitle}>Участники</div>
                    <div className={s.row}>
                        {c.members.map((m) => (
                            <Link
                                key={m.uid}
                                to={`/social_network/profile/${encodeURIComponent(m.uid)}`}
                                className={s.cardRow}
                                role="button"
                            >
                                <Avatar url={m.avatar_key} size={32} />
                                <span className={s.cardMain}>
                                    <span className={s.cardName}>{m.nickname || m.login}</span>
                                    <span className={s.cardSub}>@{m.login}</span>
                                </span>
                            </Link>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
