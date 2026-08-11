import { useEffect, useRef } from 'react';
import type { SocialGraphNode } from '../../../services/api/social';
import s from '../Social_network.module.css';

export type GraphMenuAction =
    | 'profile'
    | 'chat'
    | 'toggleFriend'
    | 'toggleJoin'
    | 'center';

interface Props {
    node: SocialGraphNode;
    x: number;
    y: number;
    viewport: { width: number; height: number };
    onAction: (action: GraphMenuAction) => void;
    onClose: () => void;
}

const MENU_W = 230;

export function GraphContextMenu({ node, x, y, viewport, onAction, onClose }: Props) {
    const ref = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) onClose();
        };
        const keyHandler = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('mousedown', handler);
        window.addEventListener('keydown', keyHandler);
        return () => {
            window.removeEventListener('mousedown', handler);
            window.removeEventListener('keydown', keyHandler);
        };
    }, [onClose]);

    const left = Math.min(x, viewport.width - MENU_W - 8);
    const top = Math.min(y, viewport.height - 220);

    const isUser = node.type === 'user';

    return (
        <div ref={ref} className={s.graphMenu} style={{ left, top, width: MENU_W }}>
            <div className={s.graphMenuTitle}>{node.label}</div>
            <button
                className={s.graphMenuItem}
                onClick={() => onAction('profile')}
            >
                Открыть профиль
            </button>
            <button
                className={s.graphMenuItem}
                onClick={() => onAction('chat')}
            >
                {isUser ? 'Написать сообщение' : 'Открыть чат сообщества'}
            </button>
            {isUser ? (
                <button
                    className={s.graphMenuItem}
                    onClick={() => onAction('toggleFriend')}
                >
                    {node.is_friend ? 'Убрать из друзей' : 'Добавить в друзья'}
                </button>
            ) : (
                <button
                    className={s.graphMenuItem}
                    onClick={() => onAction('toggleJoin')}
                >
                    {node.is_member ? 'Покинуть сообщество' : 'Вступить в сообщество'}
                </button>
            )}
            <div className={s.graphMenuDivider} />
            <button
                className={s.graphMenuItem}
                onClick={() => onAction('center')}
            >
                Центрировать
            </button>
        </div>
    );
}
