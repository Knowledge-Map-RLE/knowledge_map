import Project_title from '../Project_title';
import Site_map from '../Site_map';
import User from '../User';
import s from './Introduction.module.css';

export default function Introduction() {
  return <div className={s.container}>
    <header className={s.header}>
      <Project_title className='' />
      <div style={{ width: '100%' }}></div>
      <User className={s.user} />
    </header>
    <main>
      <div className={s.start_text}>Карта Знаний — инструмент (в разработке) для решения задачи радикального продления жизни
        <br/>
        (На заднем фоне анимация с примерами)
        </div>
      <div>Путь от идей проекта к цели РПЖ</div>
      <div>Получаем данные — Подпроект "База данных по базам данных"</div>
    </main>
    <footer className={s.footer}>
      <Site_map/>
    </footer>
  </div>
}