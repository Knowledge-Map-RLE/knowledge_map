import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faBars } from '@fortawesome/free-solid-svg-icons';
import s from './ProjectTitle.module.css';
import { SLOGAN_KEYS, LINKS, type ProjectTitleProps } from './model';
import { useTranslation } from 'react-i18next';

const ProjectTitle: React.FC<ProjectTitleProps> = ({ className = '' }) => {
    const { t } = useTranslation();
    const [isOpen, setIsOpen] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);
    const [sloganKey] = useState(() => SLOGAN_KEYS[Math.floor(Math.random() * SLOGAN_KEYS.length)]);

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    return (
        <div ref={menuRef} className={`${s.main_menu} ${className}`} onClick={() => setIsOpen(o => !o)}>
            <h1>{t('header.project.name')}</h1>
            <div className={s.slogan}>{t(sloganKey)}</div>
            <FontAwesomeIcon icon={faBars} className={`${s.arrow} ${isOpen ? s.arrow_open : ''}`} />
            {isOpen && (
                <nav className={s.dropdown}>
                    {LINKS.map(({ to, translationKey }) => (
                        <Link key={to} to={to} className={s.link} onClick={() => setIsOpen(false)}>
                            {t(translationKey)}
                        </Link>
                    ))}
                </nav>
            )}
        </div>
    );
};

export default ProjectTitle;
