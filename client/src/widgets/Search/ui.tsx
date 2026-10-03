import s from './Search.module.css';
import type { SearchProps } from './model';
import { useTranslation } from 'react-i18next';

const Search: React.FC<SearchProps> = ({ className = '' }) => {
    const { t } = useTranslation();
    return (
        <div className={`${s.search_panel} ${className}`}>
            <div className={s.logo}></div>
            <input type="text" className={s.search} placeholder={t('header.search.placeholder')} />
        </div>
    );
};

export default Search;
