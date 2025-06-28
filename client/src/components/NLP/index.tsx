import s from './NLP.module.css'

export default function NLP() {
    return <main className={s.nlp}>
        <div className={s.nlp_text}>Исходный текст с автоматической разметкой. Человек проверяет и корректирует разметку. Сравнение разных алгоритмов разметки.</div>
        <div className={s.nlp_graph}>Граф онтологии лингвистики текста</div>
        <div className={s.nlp_knowledge_map}>Как это будет добавлено в граф карты знаний?</div>
    </main>
}