import Header from '../../widgets/Header';
import styles from './Landing.module.css';
import {
    LINKS_GRID,
    FEATURES_GRID,
    FUTURE_GRID,
    PROGRESS_BARS,
    COLLAB_ITEMS,
    CONTRIBUTE_GRID,
    EDUCATION_LIST,
} from './model';
import { useTranslation } from 'react-i18next';

const LandingUI: React.FC = () => {
    const { t } = useTranslation();
    return (
        <div className={styles.page}>
            <Header showSearch={true} className={styles.header} />
            <main className={styles.main}>

                <section className={styles.hero}>
                    <div className={styles.heroGlowBlue} />
                    <div className={styles.heroGlowPurple} />
                    <div className={styles.heroInner}>
                        <div className={styles.heroBadge}>{t('landing.hero.badge')}</div>
                        <h1 className={styles.heroTitle}>
                            {t('landing.hero.title')}<br />
                            <span className={styles.heroGradientText}>{t('landing.hero.titleContinuation')}</span>
                        </h1>
                        <p className={styles.heroSubtitle}>{t('landing.hero.description')}</p>
                        <div className={styles.heroCta}>
                            <a href="https://t.me/KnowledgeMapForum" target="_blank" rel="noopener noreferrer" className={styles.ctaBtnPrimary}>
                                {t('landing.hero.join')}
                            </a>
                            <a href="https://miro.com/app/board/uXjVPyIT5F0=/?moveToWidget=3458764562951665022&cot=14" target="_blank" rel="noopener noreferrer" className={styles.ctaBtnSecondary}>
                                {t('landing.hero.viewMap')}
                            </a>
                        </div>
                        <div className={styles.partners}>
                        <span className={styles.partnersLabel}>{t('landing.hero.partners')}</span>
                            <a href="https://openlongevity.org/" target="_blank" rel="noopener noreferrer" className={styles.partnerLink}>Open Longevity</a>
                            <a href="https://t.me/OpenLongevity" target="_blank" rel="noopener noreferrer" className={styles.partnerLink}>(Telegram)</a>
                            <span className={styles.partnersSep}>{t('landing.hero.and')}</span>
                            <a href="https://scienceagainstaging.com" target="_blank" rel="noopener noreferrer" className={styles.partnerLink}>{t('landing.hero.foundation')}</a>
                        </div>
                    </div>
                    <div className={styles.heroWarning}>
                        <div className={styles.heroWarningIcon}>⚠️</div>
                        <p>
                            <strong>{t('landing.hero.warningTitle')}</strong> {t('landing.hero.warning')}
                        </p>
                    </div>
                </section>

                <section className={styles.links}>
                    <div className={styles.sectionInner}>
                        <div className={styles.linksGrid}>
                            {LINKS_GRID.map(({ href, icon, color, translationPath }) => (
                                <a key={href} href={href} target="_blank" rel="noopener noreferrer" className={styles.linkCard}>
                                    <div className={styles.linkIcon} style={{ background: color }}>{icon}</div>
                                    <div>
                            <div className={styles.linkLabel}>{t(`${translationPath}.title`)}</div>
                            <div className={styles.linkDesc}>{t(`${translationPath}.description`)}</div>
                                    </div>
                                </a>
                            ))}
                        </div>
                    </div>
                </section>

                <section className={styles.about} id="about">
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                            <h2 className={styles.sectionTitle}>{t('landing.about.title')}</h2>
                            <p className={styles.sectionSubtitle}>{t('landing.about.description')}</p>
                        </div>
                        <div className={styles.aboutGrid}>
                            <div className={`${styles.aboutCard} ${styles.aboutCardBlue}`}>
                                <div className={`${styles.aboutIcon} ${styles.aboutIconBlue}`}>⬡</div>
                                <h3>{t('landing.about.dag.title')}</h3>
                                <p>{t('landing.about.dag.description')}</p>
                            </div>
                            <div className={`${styles.aboutCard} ${styles.aboutCardPurple}`}>
                                <div className={`${styles.aboutIcon} ${styles.aboutIconPurple}`}>🤖</div>
                                <h3>{t('landing.about.scientist.title')}</h3>
                                <p>{t('landing.about.scientist.description')}</p>
                            </div>
                            <div className={`${styles.aboutCard} ${styles.aboutCardPink}`}>
                                <div className={`${styles.aboutIcon} ${styles.aboutIconPink}`}>🌐</div>
                                <h3>{t('landing.about.open.title')}</h3>
                                <p>{t('landing.about.open.description')}</p>
                            </div>
                        </div>
                    </div>
                </section>

                <section className={styles.progress}>
                    <div className={styles.sectionInner}>
                        <div className={styles.progressGrid}>
                            <div className={styles.progressCard}>
                                <h2>{t('landing.progress.title')}</h2>
                                <p>{t('landing.progress.description')}</p>
                                <div className={styles.progressBars}>
                                    {PROGRESS_BARS.map(({ translationKey, pct }) => (
                                        <div key={translationKey} className={styles.barRow}>
                                            <span>{t(translationKey)}</span>
                                            <div className={styles.barTrack}>
                                                <div className={styles.barFill} style={{ width: `${pct}%` }} />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                            <div className={styles.collab}>
                                <h2>{t('landing.progress.collaborationTitle')}</h2>
                                <p>{t('landing.progress.collaborationDescription')}</p>
                                <div className={styles.collabItems}>
                                    {COLLAB_ITEMS.map(key => (
                                        <div key={key} className={styles.collabItem}>{t(key)}</div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                <section className={styles.features} id="features">
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                            <h2 className={styles.sectionTitle}>{t('landing.features.sectionTitle')}</h2>
                            <div className={styles.titleBar} />
                        </div>
                        <div className={styles.featuresGrid}>
                            {FEATURES_GRID.map(({ color, icon, translationPath }) => (
                                <div key={translationPath} className={styles.featureCard}>
                                    <div className={styles.featureIcon} style={{ color }}>{icon}</div>
                                    <h4>{t(`${translationPath}.title`)}</h4>
                                    <p>{t(`${translationPath}.description`)}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                <section className={styles.future}>
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                            <div className={styles.futureBadge}>{t('landing.future.badge')}</div>
                            <h2 className={`${styles.sectionTitle} ${styles.sectionTitleLight}`}>{t('landing.future.title')}</h2>
                        </div>
                        <div className={styles.futureGrid}>
                            {FUTURE_GRID.map(({ translationPath }) => (
                                <div key={translationPath} className={styles.futureCard}>
                                    <h4>{t(`${translationPath}.title`)}</h4>
                                    <p>{t(`${translationPath}.description`)}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                <section className={styles.cta} id="contribute">
                    <div className={styles.ctaInner}>
                        <h2>{t('landing.callToAction.title')}</h2>
                        <p>{t('landing.callToAction.description')}</p>
                        <div className={styles.ctaButtons}>
                            <a href="https://t.me/KnowledgeMapForum" target="_blank" rel="noopener noreferrer" className={styles.ctaWhiteBtn}>{t('landing.callToAction.join')}</a>
                            <a href="https://t.me/KnowledgeMapForum/1079/1080" target="_blank" rel="noopener noreferrer" className={styles.ctaGhostBtn}>{t('landing.callToAction.support')}</a>
                        </div>
                    </div>
                </section>

                <section className={styles.contribute}>
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                        <h2 className={styles.sectionTitle}>{t('landing.contribute.sectionTitle')}</h2>
                        </div>
                        <div className={styles.contributeGrid}>
                        {CONTRIBUTE_GRID.map(({ icon, translationPath, href }) => (
                            <div key={translationPath} className={styles.contributeCard}>
                                    <div className={styles.contributeIcon}>{icon}</div>
                                <h4>{t(`${translationPath}.title`)}</h4>
                                <p>{t(`${translationPath}.description`)}</p>
                                <a href={href} target="_blank" rel="noopener noreferrer" className={styles.contributeLink}>{t(`${translationPath}.link`)} →</a>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                <section className={styles.education} id="education">
                    <div className={styles.sectionInner}>
                        <div className={styles.educationGrid}>
                            <div className={styles.educationContent}>
                            <div className={styles.educationBadge}>{t('landing.education.badge')}</div>
                            <h2>{t('landing.education.title')}</h2>
                            <p>{t('landing.education.description')} <strong>{t('landing.education.encouragement')}</strong></p>
                                <ul className={styles.educationList}>
                                {EDUCATION_LIST.map(key => <li key={key}>{t(key)}</li>)}
                                </ul>
                            </div>
                            <div className={styles.educationVisual}>
                                <div className={styles.flashcard}>
                                <div className={styles.flashcardLabel}>{t('landing.education.flashcardLabel')}</div>
                                <div className={styles.flashcardQ}>{t('landing.education.flashcardQuestion')}</div>
                                <div className={styles.flashcardA}>{t('landing.education.flashcardAnswer')}</div>
                                    <div className={styles.flashcardBtns}>
                                    <span>{t('landing.education.again')}</span>
                                    <span>{t('landing.education.good')}</span>
                                    <span>{t('landing.education.easy')}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                <section className={styles.sayforever}>
                    <div className={styles.sectionInner}>
                        <div className={styles.sayforeverInner}>
                            <div className={styles.sayforeverContent}>
                            <div className={styles.sayforeverBadge}>{t('landing.sayForever.badge')}</div>
                            <h2>{t('landing.sayForever.title')}</h2>
                            <p>{t('landing.sayForever.description')}</p>
                                <ul className={styles.sayforeverList}>
                                <li>{t('landing.sayForever.question1')}</li>
                                <li>{t('landing.sayForever.question2')}</li>
                                <li>{t('landing.sayForever.question3')}</li>
                                </ul>
                            <p className={styles.sayforeverSelf}>{t('landing.sayForever.self')}</p>
                                <a href="https://sayforever.org/" target="_blank" rel="noopener noreferrer" className={styles.sayforeverLink}>sayforever.org →</a>
                            </div>
                        </div>
                    </div>
                </section>

                <section className={styles.author}>
                    <div className={styles.sectionInner}>
                        <div className={styles.authorInner}>
                            <div className={styles.authorAvatar}>{t('landing.author.initials')}</div>
                            <h3>{t('landing.author.name')}</h3>
                            <div className={styles.authorRole}>{t('landing.author.role')}</div>
                            <blockquote className={styles.authorQuote}>{t('landing.author.quote')}</blockquote>
                            <a href="https://t.me/dima_prokofev" target="_blank" rel="noopener noreferrer" className={styles.authorTg}>Telegram: @dima_prokofev</a>
                        </div>
                    </div>
                </section>

                <section className={styles.finalCta}>
                    <a href="https://t.me/KnowledgeMapForum" target="_blank" rel="noopener noreferrer" className={styles.finalCtaBtn}>
                        {t('landing.callToAction.final')}
                    </a>
                </section>

            </main>
        </div>
    );
};

export default LandingUI;
