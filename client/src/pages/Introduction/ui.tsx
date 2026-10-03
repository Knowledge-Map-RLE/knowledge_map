import Header from '../../widgets/Header';
import { useTranslation } from 'react-i18next';
import styles from './Introduction.module.css';

const IntroductionUI: React.FC = () => {
    const { t } = useTranslation();
    return (
        <div className={styles.container}>
            <Header showSearch={true} className={styles.header} />
            <main className={styles.main}>
                <div className={styles.start_text}>
                    {t('introduction.overview')}
                    <br />
                    {t('introduction.animationNote')}
                </div>
                <div>{t('introduction.projectPath')}</div>
                <div>{t('introduction.dataSources')}</div>
            </main>
        </div>
    );
};

export default IntroductionUI;
