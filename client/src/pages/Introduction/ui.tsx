import Header from '../../widgets/Header';
import styles from './Introduction.module.css';

const IntroductionUI: React.FC = () => {
    return (
        <div className={styles.container}>
            <Header showSearch={true} className={styles.header} />
            <main className={styles.main}>
                <div className={styles.start_text}>
                    Карта Знаний — инструмент (в разработке) для решения задачи радикального продления жизни
                    <br />
                    (На заднем фоне анимация с примерами)
                </div>
                <div>Путь от идей проекта к цели РПЖ</div>
                <div>Получаем данные — Подпроект "База данных по базам данных"</div>
            </main>
        </div>
    );
};

export default IntroductionUI;
