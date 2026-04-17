import s from './Search.module.css';
import type { SearchProps } from './model';

const Search: React.FC<SearchProps> = ({ className = '' }) => {
    return (
        <div className={`${s.search_panel} ${className}`}>
            <div className={s.logo}></div>
            <input type="text" className={s.search} placeholder="Введён запрос + Enter = Поиск" />
        </div>
    );
};

export default Search;
