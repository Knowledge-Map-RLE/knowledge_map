import ProjectTitle from '../ProjectTitle';
import Search from '../Search';
import User from '../User';
import Feedback from '../Feedback';
import SubscriptionBadge from './components/SubscriptionBadge';
import LanguageSwitcher from '../../shared/i18n/LanguageSwitcher';
import s from './Header.module.css';
import type { HeaderProps } from './model';

const Header: React.FC<HeaderProps> = ({ showSearch = true, className = '' }) => {
    return (
        <header className={`${s.header} ${className}`}>
            <ProjectTitle className={s.title} />
            {showSearch
                ? <Search className={s.search} />
                : <div style={{ width: '100%' }} />
            }
            <SubscriptionBadge />
            <Feedback className={s.feedback} />
            <LanguageSwitcher className={s.languageSwitcher} />
            <User className={s.user} />
        </header>
    );
};

export default Header;
