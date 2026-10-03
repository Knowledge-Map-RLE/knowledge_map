import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import GlobalLinguisticGraph from './components/GlobalLinguisticGraph';
import PatternGraphView from './components/PatternGraphView';
import styles from './NLP.module.css';
import type { NlpTab } from './model';

export const NLP: React.FC = () => {
    const { t } = useTranslation();
    const [activeTab, setActiveTab] = useState<NlpTab>('graph');

    return (
        <main className={styles.nlp}>
            <div className={styles.tabBar}>
                <button
                    className={`${styles.tabButton} ${activeTab === 'graph' ? styles.active : ''}`}
                    onClick={() => setActiveTab('graph')}
                >
                    {t('patternAnalysis.tabs.graph')}
                </button>
                <button
                    className={`${styles.tabButton} ${activeTab === 'patterns' ? styles.active : ''}`}
                    onClick={() => setActiveTab('patterns')}
                >
                    {t('patternAnalysis.tabs.patterns')}
                </button>
            </div>

            <div className={styles.content}>
                {activeTab === 'graph' && <GlobalLinguisticGraph />}
                {activeTab === 'patterns' && <PatternGraphView />}
            </div>
        </main>
    );
};

export default NLP;
