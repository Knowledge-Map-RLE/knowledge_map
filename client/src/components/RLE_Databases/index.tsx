import { Link } from 'react-router-dom';
import Project_title from '../Project_title';
import User from '../User';
import s from './RLE_Databases.module.css';
import Site_map from '../Site_map';

export default function RLE_Databases() {
  return <div className={s.container}>
    <header className={s.header}>
      <Project_title className='' />
      <div style={{ width: '100%' }}></div>
      <User className={s.user} />
    </header>
    <main>
      <div className={s.start_text}>Подпроект Карты Знаний "Базы данных РПЖ" — базы данных релевантные задаче радикального продления жизни.
      </div>
      <div>
        Здесь можно сделать уровни организации живой материи и для каждого уровня начиная с наиболее высокого (экологический, эволюционный, организменный) и заканчивая нижними (клетка, ген, вещество, химия, физика). В начале прокрутки страницы должны быть показаны только те БД которые относятся к самомму верхнему уровню, затем при спуске вниз, анимацией подтягиваются следующие, а неактуальные удаляются сверху. Так будет реализован принцип сверху вниз как в Карте Знаний. Анимация будет сопровождаться сменой заднего фона соответствующим уровню организации. Анимация может быть как сверху вниз, так и удалением отдалением камеры как в Spore.
        <a href=''>Сылка</a>
      </div>
    </main>
    <footer className={s.footer}>
      <Site_map/>
    </footer>
  </div>
}