/**
 * NLP страница — объединённый лингвистический граф всех статей + паттерны как графы.
 */
import { useState } from 'react'
import GlobalLinguisticGraph from './GlobalLinguisticGraph'
import PatternGraphView from './PatternGraphView'
import s from './NLP.module.css'

type NlpTab = 'graph' | 'patterns'

export default function NLP() {
    const [activeTab, setActiveTab] = useState<NlpTab>('graph')

    return (
        <main className={s.nlp}>
            <div className={s.tabBar}>
                <button
                    className={`${s.tabButton} ${activeTab === 'graph' ? s.active : ''}`}
                    onClick={() => setActiveTab('graph')}
                >
                    Граф
                </button>
                <button
                    className={`${s.tabButton} ${activeTab === 'patterns' ? s.active : ''}`}
                    onClick={() => setActiveTab('patterns')}
                >
                    Паттерны
                </button>
            </div>

            <div className={s.content}>
                {activeTab === 'graph' && <GlobalLinguisticGraph />}
                {activeTab === 'patterns' && <PatternGraphView />}
            </div>
        </main>
    )
}
