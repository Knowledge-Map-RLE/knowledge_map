import s from './Knowledge_map_ui.module.css'
import Header from '../Header'
import { Link } from 'react-router-dom'

export default function Knowledge_map_ui() {
    return <div className={s.interface}>
        <Header showSearch={true} className={s.header} />
        <div className={`${s.left} ${s.panel}`}>
            <h2 className={s.menu_title}>Меню</h2>
            <nav className={s.main_menu}>
                <Link to="/">Карта знаний</Link>
                <Link to="/introduction">Введение</Link>
                <Link to="/science_articles" title='Подпроект'>Карта научных статей</Link>
                <Link to="/data_extraction" title="Исходник → Markdown и данные">Извлечение данных</Link>
                <Link to="/nlp">Лингвистика</Link>
            </nav>
        </div>
        <div className={`${s.center} ${s.panel}`}> </div>
        <div className={`${s.right} ${s.panel}`}>
            <h2>Вклад пользователя в РПЖ</h2>
            <div>
                <div>Времязатраты: 125ч</div>
                <div>Блоков: 423</div>
                <div>Связей: 243</div>
                <div>Разметок: 538</div>
                <div>Отмечено аллиасов: 683</div>
                <div>Паттернов: 12</div>
                <div>Решено противоречий: 51</div>
                <div>Успешных паттернов: 12</div>
                <div>Открытий: 2</div>
                <div>Ускорение науки: 5% (Вы как сотня учёных, так держать!)</div>
            </div>

            <h2>Текущие тренды</h2>
            <div>
                <div>1</div>
                <div>2</div>
                <div>3</div>
                <div>4</div>
                <div>5</div>
                <div>6</div>
                <div>7</div>
                <div>8</div>
            </div>
        </div>
        <div className={`${s.info} ${s.panel}`}> </div>
        <div className={`${s.bot} ${s.panel}`}> </div>
        <div className={`${s.minimap} ${s.panel}`}>🗺️ + Избранные блоки</div>
    </div>
}