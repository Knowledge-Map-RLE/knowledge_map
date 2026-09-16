import { useState } from 'react';
import Providers from './Providers';
import Pricing from './Pricing';
import styles from '../../Admin.module.css';

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<'providers' | 'pricing'>('providers');

  return (
    <div>
      <h1>Настройки</h1>

      <div className={styles.tabsBar}>
        <button
          className={`${styles.tabBtn} ${activeTab === 'providers' ? styles.tabBtnActive : ''}`}
          onClick={() => setActiveTab('providers')}
        >
          AI Провайдеры
        </button>
        <button
          className={`${styles.tabBtn} ${activeTab === 'pricing' ? styles.tabBtnActive : ''}`}
          onClick={() => setActiveTab('pricing')}
        >
          Тарифы
        </button>
      </div>

      {activeTab === 'providers' && <Providers />}
      {activeTab === 'pricing' && <Pricing />}
    </div>
  );
}
