import { useCallback, useEffect, useRef, useState } from 'react';
import { MdPerson } from 'react-icons/md';
import s from './Modal.module.css';
import {
    createCommunity,
    decodeContacts,
    deleteCommunity,
    getMe,
    getMyCommunities,
    PROFILE_UPDATED_EVENT,
    socialImageUrl,
    updateCommunity,
    updateProfile,
    uploadImage,
    type CommunitySummary,
    type SocialContacts,
    type SocialUserProfile,
} from '../../../services/api/social';
import { useToast } from '../../../shared/ui/Toast';

interface AccountModalProps {
    myUid: string;
    onClose: () => void;
}

type Tab = 'profile' | 'communities';

const CONTACT_FIELDS: Array<{ key: keyof SocialContacts; label: string; placeholder: string }> = [
    { key: 'email', label: 'Email', placeholder: 'user@example.com' },
    { key: 'telegram', label: 'Telegram', placeholder: '@username' },
    { key: 'phone', label: 'Телефон', placeholder: '+7 (900) 000-00-00' },
    { key: 'website', label: 'Сайт', placeholder: 'https://example.com' },
];

const btnTab = (active: boolean) =>
    `px-3 py-2 text-sm font-semibold rounded-md transition-colors ${
        active ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100'
    }`;

export const AccountModal: React.FC<AccountModalProps> = ({ onClose }) => {
    const { error: toastError, success: toastSuccess } = useToast();
    const fileRef = useRef<HTMLInputElement>(null);
    const [tab, setTab] = useState<Tab>('profile');
    const [profile, setProfile] = useState<SocialUserProfile | null>(null);
    const [bio, setBio] = useState('');
    const [avatarKey, setAvatarKey] = useState('');
    const [contacts, setContacts] = useState<SocialContacts>({});
    const [uploading, setUploading] = useState(false);
    const [savingProfile, setSavingProfile] = useState(false);
    const [communities, setCommunities] = useState<CommunitySummary[]>([]);
    const [loadingComms, setLoadingComms] = useState(false);
    const [newName, setNewName] = useState('');
    const [newDesc, setNewDesc] = useState('');
    const [creating, setCreating] = useState(false);
    const [editing, setEditing] = useState<Record<string, { name: string; description: string }>>({});
    const [savingComm, setSavingComm] = useState<string | null>(null);
    const [deleting, setDeleting] = useState<string | null>(null);

    const loadProfile = useCallback(async () => {
        try {
            const res = await getMe();
            setProfile(res.profile ?? null);
            setBio(res.profile?.bio ?? '');
            setAvatarKey(res.profile?.avatar_key ?? '');
            setContacts(decodeContacts(res.profile?.contacts));
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки профиля');
        }
    }, [toastError]);

    const loadCommunities = useCallback(async () => {
        setLoadingComms(true);
        try {
            const res = await getMyCommunities();
            setCommunities(res.communities ?? []);
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки сообществ');
        } finally {
            setLoadingComms(false);
        }
    }, [toastError]);

    useEffect(() => {
        loadProfile();
        loadCommunities();
    }, [loadProfile, loadCommunities]);

    const handleUploadAvatar = async (file: File | undefined) => {
        if (!file) return;
        setUploading(true);
        try {
            const res = await uploadImage(file);
            if (res.success && res.object_key) {
                setAvatarKey(res.object_key);
                toastSuccess('Аватар загружен — нажмите «Сохранить»');
            } else {
                toastError(res.error || 'Ошибка загрузки аватара');
            }
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки аватара');
        } finally {
            setUploading(false);
        }
    };

    const handleSaveProfile = async () => {
        setSavingProfile(true);
        try {
            const res = await updateProfile({
                bio: bio.trim(),
                avatar_key: avatarKey.trim(),
                contacts,
            });
            if (res.success) {
                toastSuccess('Профиль сохранён');
                window.dispatchEvent(new Event(PROFILE_UPDATED_EVENT));
                window.dispatchEvent(new Event('social:graph-refresh'));
            } else {
                toastError(res.error || 'Ошибка сохранения');
            }
            await loadProfile();
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка сохранения');
        } finally {
            setSavingProfile(false);
        }
    };

    const handleCreate = async () => {
        if (!newName.trim()) return;
        setCreating(true);
        try {
            const res = await createCommunity({ name: newName.trim(), description: newDesc.trim() });
            if (res.success) {
                toastSuccess('Сообщество создано');
                setNewName('');
                setNewDesc('');
                await loadCommunities();
            } else {
                toastError(res.error || 'Ошибка создания');
            }
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка создания');
        } finally {
            setCreating(false);
        }
    };

    const handleUpdate = async (c: CommunitySummary) => {
        const ed = editing[c.uid];
        if (!ed) return;
        setSavingComm(c.uid);
        try {
            const res = await updateCommunity(c.uid, {
                name: ed.name.trim(),
                description: ed.description.trim(),
            });
            if (res.success) {
                toastSuccess('Сообщество сохранено');
            } else {
                toastError(res.error || 'Ошибка сохранения');
            }
            setEditing((prev) => {
                const next = { ...prev };
                delete next[c.uid];
                return next;
            });
            await loadCommunities();
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка сохранения');
        } finally {
            setSavingComm(null);
        }
    };

    const handleDelete = async (c: CommunitySummary) => {
        if (!window.confirm(`Удалить сообщество «${c.name}»? Это действие необратимо.`)) return;
        setDeleting(c.uid);
        try {
            const res = await deleteCommunity(c.uid);
            if (res.success) {
                toastSuccess('Сообщество удалено');
            } else {
                toastError(res.error || 'Ошибка удаления');
            }
            await loadCommunities();
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка удаления');
        } finally {
            setDeleting(null);
        }
    };

    return (
        <div className={s.overlay} onClick={onClose}>
            <div
                className={s.modal}
                style={{ maxWidth: 640 }}
                onClick={(e) => e.stopPropagation()}
            >
                <div className={s.header}>
                    <h2>Личный кабинет</h2>
                    <button onClick={onClose} className={s.close_button}>×</button>
                </div>
                <div className="px-6 pt-4 flex gap-2">
                    <button className={btnTab(tab === 'profile')} onClick={() => setTab('profile')}>Профиль</button>
                    <button className={btnTab(tab === 'communities')} onClick={() => setTab('communities')}>
                        Мои сообщества
                    </button>
                </div>

                {tab === 'profile' ? (
                    <div className={s.form}>
                        <div className={s.field}>
                            <label>Имя</label>
                            <input type="text" value={profile?.nickname ?? ''} disabled className={s.input} />
                            <div className={s.hint}>Никнейм меняется только администратором</div>
                        </div>
                        <div className={s.field}>
                            <label>Логин</label>
                            <input type="text" value={`@${profile?.login ?? ''}`} disabled className={s.input} />
                        </div>
                        <div className={s.field}>
                            <label>Аватар</label>
                            <div className="flex items-center gap-3">
                                <button
                                    type="button"
                                    className="relative cursor-pointer disabled:opacity-50"
                                    onClick={() => fileRef.current?.click()}
                                    disabled={uploading}
                                    title={uploading ? 'Загрузка…' : 'Нажмите, чтобы загрузить изображение'}
                                    aria-label="Загрузить аватар"
                                >
                                    {avatarKey ? (
                                        <img
                                            src={socialImageUrl(avatarKey)}
                                            alt="Аватар"
                                            className="w-12 h-12 rounded-full object-cover border-2 border-gray-200 hover:ring-2 hover:ring-blue-300 transition"
                                        />
                                    ) : (
                                        <div className="w-12 h-12 rounded-full bg-blue-50 border-2 border-blue-100 flex items-center justify-center text-2xl hover:ring-2 hover:ring-blue-300 transition">
                                            {uploading ? '…' : <MdPerson />}
                                        </div>
                                    )}
                                </button>
                                {avatarKey && (
                                    <button
                                        type="button"
                                        className="bg-gray-100 text-gray-700 text-sm px-3 py-1.5 rounded-md hover:bg-gray-200"
                                        onClick={() => setAvatarKey('')}
                                    >
                                        Убрать
                                    </button>
                                )}
                                <input
                                    ref={fileRef}
                                    type="file"
                                    accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml"
                                    className="hidden"
                                    onChange={(e) => void handleUploadAvatar(e.target.files?.[0])}
                                />
                            </div>
                        </div>
                        <div className={s.field}>
                            <label>О себе</label>
                            <textarea
                                value={bio}
                                onChange={(e) => setBio(e.target.value)}
                                className={s.input}
                                rows={4}
                                placeholder="Расскажите о себе"
                            />
                        </div>
                        <div className={s.field}>
                            <label>Контакты</label>
                            <div className="space-y-2">
                                {CONTACT_FIELDS.map(({ key, label, placeholder }) => (
                                    <input
                                        key={key}
                                        type="text"
                                        value={contacts[key] ?? ''}
                                        onChange={(e) => setContacts((prev) => ({ ...prev, [key]: e.target.value }))}
                                        className={s.input}
                                        placeholder={placeholder}
                                        aria-label={label}
                                    />
                                ))}
                            </div>
                        </div>
                        <div className={s.actions}>
                            <button
                                className={s.submit_button}
                                onClick={handleSaveProfile}
                                disabled={savingProfile || uploading}
                            >
                                {savingProfile ? 'Сохранение…' : 'Сохранить'}
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="p-6 space-y-4">
                        <div className="space-y-2">
                            <div className="text-sm font-semibold text-gray-800">Создать сообщество</div>
                            <input
                                className={s.input}
                                placeholder="Название"
                                value={newName}
                                onChange={(e) => setNewName(e.target.value)}
                            />
                            <input
                                className={s.input}
                                placeholder="Описание (необязательно)"
                                value={newDesc}
                                onChange={(e) => setNewDesc(e.target.value)}
                            />
                            <button
                                className={s.submit_button}
                                onClick={handleCreate}
                                disabled={creating || !newName.trim()}
                            >
                                {creating ? 'Создание…' : 'Создать'}
                            </button>
                        </div>
                        <div className="border-t pt-4">
                            <div className="text-sm font-semibold text-gray-800 mb-2">Мои сообщества</div>
                            {loadingComms ? (
                                <div className="text-sm text-gray-500">Загрузка…</div>
                            ) : communities.length === 0 ? (
                                <div className="text-sm text-gray-400">Вы пока не создали ни одного сообщества</div>
                            ) : (
                                <div className="space-y-3">
                                    {communities.map((c) => {
                                        const isEditing = !!editing[c.uid];
                                        const ed = editing[c.uid] ?? { name: c.name, description: c.description };
                                        return (
                                            <div key={c.uid} className="border rounded-lg p-3 space-y-2">
                                                {isEditing ? (
                                                    <>
                                                        <input
                                                            className={s.input}
                                                            value={ed.name}
                                                            onChange={(e) =>
                                                                setEditing((prev) => ({ ...prev, [c.uid]: { ...ed, name: e.target.value } }))
                                                            }
                                                        />
                                                        <input
                                                            className={s.input}
                                                            value={ed.description}
                                                            onChange={(e) =>
                                                                setEditing((prev) => ({ ...prev, [c.uid]: { ...ed, description: e.target.value } }))
                                                            }
                                                        />
                                                        <div className="flex gap-2">
                                                            <button
                                                                className="bg-blue-600 text-white text-sm px-3 py-1.5 rounded-md hover:bg-blue-700 disabled:opacity-50"
                                                                onClick={() => handleUpdate(c)}
                                                                disabled={savingComm === c.uid}
                                                            >
                                                                {savingComm === c.uid ? 'Сохранение…' : 'Сохранить'}
                                                            </button>
                                                            <button
                                                                className="bg-gray-100 text-gray-700 text-sm px-3 py-1.5 rounded-md hover:bg-gray-200"
                                                                onClick={() =>
                                                                    setEditing((prev) => {
                                                                        const next = { ...prev };
                                                                        delete next[c.uid];
                                                                        return next;
                                                                    })
                                                                }
                                                            >
                                                                Отмена
                                                            </button>
                                                        </div>
                                                    </>
                                                ) : (
                                                    <>
                                                        <div className="flex items-center justify-between gap-2">
                                                            <div className="min-w-0">
                                                                <div className="font-semibold text-gray-900 truncate">{c.name}</div>
                                                                <div className="text-xs text-gray-500">
                                                                    {c.member_count} участников
                                                                    {c.description ? ` · ${c.description}` : ''}
                                                                </div>
                                                            </div>
                                                            <div className="flex gap-2 flex-shrink-0">
                                                                <button
                                                                    className="bg-gray-100 text-gray-700 text-sm px-3 py-1.5 rounded-md hover:bg-gray-200"
                                                                    onClick={() => setEditing((prev) => ({ ...prev, [c.uid]: { name: c.name, description: c.description } }))}
                                                                >
                                                                    Изменить
                                                                </button>
                                                                <button
                                                                    className="bg-red-50 text-red-600 text-sm px-3 py-1.5 rounded-md hover:bg-red-100 disabled:opacity-50"
                                                                    onClick={() => handleDelete(c)}
                                                                    disabled={deleting === c.uid}
                                                                >
                                                                    {deleting === c.uid ? '…' : 'Удалить'}
                                                                </button>
                                                            </div>
                                                        </div>
                                                    </>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};
