import { useState } from 'react';
import GlobalLinguisticGraph from './components/GlobalLinguisticGraph';
import PatternGraphView from './components/PatternGraphView';
import styles from './NLP.module.css';
import type { NlpTab } from './model';

export const NLP: React.FC = () => {
    const [activeTab, setActiveTab] = useState<NlpTab>('graph');

    return (
        <main className={styles.nlp}>
            <div className={styles.tabBar}>
                <button
                    className={`${styles.tabButton} ${activeTab === 'graph' ? styles.active : ''}`}
                    onClick={() => setActiveTab('graph')}
                >
                    Граф
                </button>
                <button
                    className={`${styles.tabButton} ${activeTab === 'patterns' ? styles.active : ''}`}
                    onClick={() => setActiveTab('patterns')}
                >
                    Паттерны
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
