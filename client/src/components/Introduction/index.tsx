import Header from '../Header';
import s from './Introduction.module.css';

export default function Introduction() {
  return <div className={s.container}>
    <Header showSearch={false} className={s.header} />
    <main>
      <div className={s.start_text}>Карта Знаний — инструмент (в разработке) для решения задачи радикального продления жизни
        <br/>
        (На заднем фоне анимация с примерами)
        </div>
      <div>Путь от идей проекта к цели РПЖ</div>
      <div>Получаем данные — Подпроект "База данных по базам данных"</div>
    </main>
  </div>
}