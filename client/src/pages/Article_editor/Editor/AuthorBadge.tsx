import React from 'react';
import type { AuthorInfo } from '../model';

interface AuthorBadgeProps {
    author?: AuthorInfo | null;
    label?: string;
}

/** Значок «Автор» с tooltip-подсказкой (никнейм + логин), либо нейтральная
 *  иконка без данных об авторе. */
const AuthorBadge: React.FC<AuthorBadgeProps> = ({ author, label }) => {
    let tooltip: string;
    if (author) {
        const name = author.nickname || author.login || author.uid;
        const atLogin = author.login && author.login !== name ? ` (@${author.login})` : '';
        tooltip = `${label ? `${label}: ` : ''}${name}${atLogin}`;
    } else {
        tooltip = label ? `${label}: неизвестен` : 'Автор неизвестен';
    }
    return (
        <span
            title={tooltip}
            style={{
                display: 'inline-flex',
                alignItems: 'center',
                cursor: 'help',
                color: '#6b7280',
                flexShrink: 0,
            }}
        >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
            </svg>
        </span>
    );
};

export default React.memo(AuthorBadge);
