/**
 * NLP страница — объединённый лингвистический граф всех статей.
 * Обвязка (header, контейнер) сохранена, заменён только внутренний контент.
 */
import GlobalLinguisticGraph from './GlobalLinguisticGraph'
import s from './NLP.module.css'

export default function NLP() {
    return (
        <main className={s.nlp}>
            <GlobalLinguisticGraph />
        </main>
    )
}
