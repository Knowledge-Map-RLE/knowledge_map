import { Link, useLocation } from 'react-router-dom';
import { FaChartLine, FaUsers, FaCoins, FaMoneyBillWave, FaReceipt, FaChartPie, FaBalanceScale, FaCog, FaRocket, FaBoxes, FaBullseye } from 'react-icons/fa';
import type { IconType } from 'react-icons';
import styles from '../Admin.module.css';

interface SidebarItem {
  label: string;
  path: string;
  icon: IconType;
}

const NAV_ITEMS: SidebarItem[] = [
  { label: 'Обзор', path: '/admin', icon: FaChartLine },
  { label: 'Пользователи', path: '/admin/users', icon: FaUsers },
  { label: 'Токены', path: '/admin/tokens', icon: FaCoins },
  { label: 'Продажи', path: '/admin/sales', icon: FaMoneyBillWave },
  { label: 'Расходы', path: '/admin/expenses', icon: FaReceipt },
  { label: 'Прибыльность', path: '/admin/profitability', icon: FaChartPie },
  { label: 'План → Факт', path: '/admin/plan', icon: FaBalanceScale },
  { label: 'Настройки', path: '/admin/settings', icon: FaCog },
  { label: 'Стратегия', path: '/admin/strategy', icon: FaRocket },
  { label: 'Unit Economics', path: '/admin/unit-economics', icon: FaBoxes },
  { label: 'Запуск', path: '/admin/launch', icon: FaBullseye },
];

export default function AdminSidebar() {
  const location = useLocation();

  const isActive = (path: string) => {
    if (path === '/admin') {
      return location.pathname === '/admin';
    }
    return location.pathname.startsWith(path);
  };

  return (
    <aside className={styles.adminSidebar}>
      <div className={styles.sidebarHeader}>
        <h2>Knowledge Map</h2>
        <span>Admin Panel</span>
      </div>
      <nav className={styles.sidebarNav}>
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`${styles.sidebarLink} ${isActive(item.path) ? styles.sidebarLinkActive : ''}`}
          >
            <span className={styles.sidebarIcon}>
              <item.icon size={16} />
            </span>
            {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
