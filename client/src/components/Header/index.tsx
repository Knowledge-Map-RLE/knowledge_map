import Project_title from '../Project_title';
import Search from '../Search';
import User from '../User';
import s from './Header.module.css';

interface HeaderProps {
  showSearch?: boolean;
  className?: string;
}

export default function Header({ showSearch = true, className = '' }: HeaderProps) {
  return (
    <header className={`${s.header} ${className}`}>
      <Project_title className={s.title} />
      {showSearch
        ? <Search className={s.search} />
        : <div style={{ width: '100%' }} />
      }
      <User className={s.user} />
    </header>
  );
}
