import { useCallback, useEffect, useState } from 'react';
import {
    addWallComment,
    createWallPost,
    getWall,
    type WallPost,
} from '../../../services/api/social';
import { useAuth } from '../../../entities/auth';
import { useRequireAuth } from '../../../shared/hooks/useRequireAuth';
import { useToast } from '../../../shared/ui/Toast';
import { MarkdownContent } from '../../../shared/ui/MarkdownContent';
import { formatTime } from '../model';
import s from '../Social_network.module.css';

function pluralComments(n: number): string {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return 'комментарий';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'комментария';
    return 'комментариев';
}

export function Wall({ uid, isMe }: { uid: string; isMe: boolean }) {
    const { isAuthenticated } = useAuth();
    const requireAuth = useRequireAuth();
    const toast = useToast();
    const [posts, setPosts] = useState<WallPost[]>([]);
    const [loading, setLoading] = useState(true);
    const [newPost, setNewPost] = useState('');
    const [posting, setPosting] = useState(false);
    const [commenting, setCommenting] = useState<string | null>(null);
    const [drafts, setDrafts] = useState<Record<string, string>>({});

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const res = await getWall(uid);
            if (res.success) setPosts(res.posts ?? []);
        } catch (e) {
            toast.error(e instanceof Error ? e.message : 'Ошибка загрузки стены');
        } finally {
            setLoading(false);
        }
    }, [uid, toast]);

    useEffect(() => {
        void load();
    }, [load]);

    const handlePost = async () => {
        if (!isMe) return;
        const text = newPost.trim();
        if (!text) return;
        setPosting(true);
        try {
            const res = await createWallPost(uid, text);
            if (res.success) {
                setNewPost('');
                toast.success('Запись опубликована');
                await load();
            } else {
                toast.error(res.error || 'Ошибка публикации');
            }
        } catch (e) {
            toast.error(e instanceof Error ? e.message : 'Ошибка публикации');
        } finally {
            setPosting(false);
        }
    };

    const handleComment = async (postUid: string) => {
        if (!isAuthenticated) {
            requireAuth('Войдите или зарегистрируйтесь, чтобы комментировать');
            return;
        }
        const text = (drafts[postUid] ?? '').trim();
        if (!text) return;
        setCommenting(postUid);
        try {
            const res = await addWallComment(postUid, text);
            if (res.success) {
                setDrafts((prev) => ({ ...prev, [postUid]: '' }));
                toast.success('Комментарий добавлен');
                await load();
            } else {
                toast.error(res.error || 'Ошибка добавления комментария');
            }
        } catch (e) {
            toast.error(e instanceof Error ? e.message : 'Ошибка добавления комментария');
        } finally {
            setCommenting(null);
        }
    };

    return (
        <div className={s.profileSection}>
            <div className={s.panelTitle}>Стена</div>

            {isMe && (
                <div className={s.wallComposer}>
                    <textarea
                        className={s.textarea}
                        value={newPost}
                        onChange={(e) => setNewPost(e.target.value)}
                        placeholder="Что у вас нового? Markdown поддерживается"
                        rows={3}
                    />
                    <div className={s.row}>
                        <button className={s.primaryBtn} onClick={handlePost} disabled={posting || !newPost.trim()}>
                            {posting ? 'Публикация…' : 'Опубликовать'}
                        </button>
                    </div>
                </div>
            )}

            {loading ? (
                <div className={s.hint}>Загрузка…</div>
            ) : posts.length === 0 ? (
                <div className={s.wallEmpty}>
                    {isMe ? 'У вас пока нет записей. Опубликуйте первую!' : 'На стене пока нет записей.'}
                </div>
            ) : (
                <div className={s.wallList}>
                    {posts.map((post) => (
                        <div key={post.uid} className={s.wallPost}>
                            <div className={s.wallPostBody}>
                                <div className={s.wallPostText}>
                                    <MarkdownContent value={post.text} />
                                </div>
                                <div className={s.wallPostMeta}>
                                    <span>{formatTime(post.created_at)}</span>
                                    <span>
                                        {post.comment_count > 0
                                            ? `${post.comment_count} ${pluralComments(post.comment_count)}`
                                            : 'Нет комментариев'}
                                    </span>
                                </div>
                            </div>

                            {post.comments.length > 0 && (
                                <div className={s.wallComments}>
                                    {post.comments.map((c) => (
                                        <div key={c.uid} className={s.wallComment}>
                                            <div className={s.wallCommentHead}>
                                                <span className={s.wallCommentAuthor}>
                                                    {c.author_nickname || c.author_login || 'Пользователь'}
                                                    {c.author_login ? ` @${c.author_login}` : ''}
                                                </span>
                                                <span className={s.wallCommentTime}>{formatTime(c.created_at)}</span>
                                            </div>
                                            <div className={s.wallCommentText}>
                                                <MarkdownContent value={c.text} />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}

                            <div className={s.wallCommentComposer}>
                                {isAuthenticated ? (
                                    <>
                                        <input
                                            className={s.input}
                                            value={drafts[post.uid] ?? ''}
                                            onChange={(e) =>
                                                setDrafts((prev) => ({ ...prev, [post.uid]: e.target.value }))
                                            }
                                            placeholder="Написать комментарий…"
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter') void handleComment(post.uid);
                                            }}
                                        />
                                        <button
                                            className={s.ghostBtn}
                                            onClick={() => void handleComment(post.uid)}
                                            disabled={commenting === post.uid || !(drafts[post.uid] ?? '').trim()}
                                        >
                                            {commenting === post.uid ? '…' : 'Комментировать'}
                                        </button>
                                    </>
                                ) : (
                                    <button className={s.ghostBtn} onClick={() => void handleComment(post.uid)}>
                                        Войти, чтобы комментировать
                                    </button>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
