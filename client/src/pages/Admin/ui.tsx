import { Outlet } from 'react-router-dom';
import AdminGuard from './components/AdminGuard';
import AdminSidebar from './components/AdminSidebar';
import LanguageSwitcher from '../../shared/i18n/LanguageSwitcher';
import styles from './Admin.module.css';

export default function AdminLayout() {
  return (
    <AdminGuard>
      <div className={styles.adminLayout}>
        <LanguageSwitcher className={styles.languageSwitcher} />
        <AdminSidebar />
        <main className={styles.adminContent}>
          <Outlet />
        </main>
      </div>
    </AdminGuard>
  );
}
