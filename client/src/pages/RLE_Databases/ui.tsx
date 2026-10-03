import { Link } from 'react-router-dom';
import Header from '../../widgets/Header';
import { useTranslation } from 'react-i18next';
import styles from './RLE_Databases.module.css';

const RLE_DatabasesUI: React.FC = () => {
    const { t } = useTranslation();
    return (
        <div className={styles.container}>
            <Header showSearch={true} className={styles.header} />
            <main className={styles.main}>
                <div className={styles.start_text}>
                    {t('rleDatabases.intro')}
                </div>
                <div>
                    {t('rleDatabases.description')}
                    <a href=''>{t('rleDatabases.link')}</a>
                </div>
            </main>
        </div>
    );
};

export default RLE_DatabasesUI;
