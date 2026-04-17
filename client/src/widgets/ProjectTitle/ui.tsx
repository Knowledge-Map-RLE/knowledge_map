import { useState } from 'react';
import { Link } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faBars } from '@fortawesome/free-solid-svg-icons';
import s from './ProjectTitle.module.css';
import { SLOGANS, LINKS, type ProjectTitleProps } from './model';

const ProjectTitle: React.FC<ProjectTitleProps> = ({ className = '' }) => {
    const [isOpen, setIsOpen] = useState(false);

    const randomSlogan = SLOGANS[Math.floor(Math.random() * SLOGANS.length)];

    return (
        <div className={`${s.main_menu} ${className}`} onClick={() => setIsOpen(o => !o)}>
            <h1>КАРТА ЗНАНИЙ</h1>
            <div className={s.slogan}>{randomSlogan}</div>
            <FontAwesomeIcon icon={faBars} className={`${s.arrow} ${isOpen ? s.arrow_open : ''}`} />
            {isOpen && (
                <nav className={s.dropdown}>
                    {LINKS.map(({ to, label }) => (
                        <Link key={to} to={to} className={s.link} onClick={() => setIsOpen(false)}>
                            {label}
                        </Link>
                    ))}
                </nav>
            )}
        </div>
    );
};

export default ProjectTitle;
