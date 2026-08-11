import { useCallback, useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Header from '../../widgets/Header';
import { useAuth } from '../../entities/auth';
import { TABS, type ChatTarget, type SocialTabId } from './model';
import { ChatPanel } from './components/ChatPanel';
import { FriendsPanel } from './components/FriendsPanel';
import { CommunitiesPanel } from './components/CommunitiesPanel';
import { ProfilePanel } from './components/ProfilePanel';
import { TrendsPanel } from './components/TrendsPanel';
import { NetworkGraph } from './components/NetworkGraph';
import s from './Social_network.module.css';

const SocialNetworkUI: React.FC = () => {
    const { isAuthLoading, user } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const [activeTab, setActiveTab] = useState<SocialTabId>('profile');
    const [chatTarget, setChatTarget] = useState<ChatTarget | null>(null);

    useEffect(() => {
        const st = (location.state ?? null) as { chat?: ChatTarget; tab?: SocialTabId } | null;
        if (!st) return;
        if (st.chat) {
            setChatTarget(st.chat);
            setActiveTab('chat');
        } else if (st.tab) {
            setActiveTab(st.tab);
        }
        navigate(location.pathname, { replace: true, state: null });
    }, [location.state, location.pathname, navigate]);

    const openProfile = useCallback((uid: string) => {
        navigate(`/social_network/profile/${encodeURIComponent(uid)}`);
    }, [navigate]);

    const openChat = useCallback((target: ChatTarget) => {
        setChatTarget(target);
        setActiveTab('chat');
    }, []);

    const handleGraphChat = useCallback((type: 'user' | 'community', uid: string) => {
        openChat({ type, uid, label: '' });
    }, [openChat]);

    if (isAuthLoading) {
        return (
            <div className={s.page}>
                <Header className={s.header} />
                <main className={s.main}>
                    <div className={s.gateCard}>Загрузка…</div>
                </main>
            </div>
        );
    }

    const myUid = user?.uid ?? '';

    return (
        <div className={s.page}>
            <Header className={s.header} />
            <main className={s.main}>
                <div className={s.grid2}>
                    <section className={s.centerCol}>
                        <nav className={s.tabs}>
                            {TABS.map((tab) => (
                                <button
                                    key={tab.id}
                                    className={activeTab === tab.id ? `${s.tab} ${s.tabActive}` : s.tab}
                                    onClick={() => setActiveTab(tab.id)}
                                >
                                    <span className={s.tabIcon}><tab.icon /></span>
                                    {tab.label}
                                </button>
                            ))}
                        </nav>
                        <div className={s.content}>
                            {activeTab === 'profile' && <ProfilePanel />}
                            {activeTab === 'chat' && <ChatPanel target={chatTarget} onOpenTarget={setChatTarget} myUid={myUid} />}
                            {activeTab === 'friends' && <FriendsPanel onOpenChat={openChat} />}
                            {activeTab === 'communities' && <CommunitiesPanel onOpenChat={openChat} />}
                            {activeTab === 'trends' && <TrendsPanel onOpenChat={openChat} />}
                        </div>
                    </section>
                    <aside className={s.sideRight}>
                        <NetworkGraph
                            compact
                            myUid={myUid}
                            onOpenChat={handleGraphChat}
                            onOpenProfile={openProfile}
                        />
                    </aside>
                </div>
            </main>
        </div>
    );
};

export default SocialNetworkUI;
