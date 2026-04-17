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

const LandingUI: React.FC = () => {
    return (
        <div className={styles.page}>
            <Header showSearch={true} className={styles.header} />
            <main className={styles.main}>

                <section className={styles.hero}>
                    <div className={styles.heroGlowBlue} />
                    <div className={styles.heroGlowPurple} />
                    <div className={styles.heroInner}>
                        <div className={styles.heroBadge}>Open Science Initiative</div>
                        <h1 className={styles.heroTitle}>
                            Победить старение.<br />
                            <span className={styles.heroGradientText}>Жить, сколько хочешь.</span>
                        </h1>
                        <p className={styles.heroSubtitle}>
                            Карта Знаний — технологическая карта достижения радикального продления жизни человека (РПЖ).
                            Автоматизированный ИИ-учёный, соединяющий науку, данные и человека.
                        </p>
                        <div className={styles.heroCta}>
                            <a href="https://t.me/KnowledgeMapForum" target="_blank" rel="noopener noreferrer" className={styles.ctaBtnPrimary}>
                                Присоединиться
                            </a>
                            <a href="https://miro.com/app/board/uXjVPyIT5F0=/?moveToWidget=3458764562951665022&cot=14" target="_blank" rel="noopener noreferrer" className={styles.ctaBtnSecondary}>
                                Посмотреть карту
                            </a>
                        </div>
                        <div className={styles.partners}>
                            <span className={styles.partnersLabel}>Совместно с:</span>
                            <a href="https://openlongevity.org/" target="_blank" rel="noopener noreferrer" className={styles.partnerLink}>Open Longevity</a>
                            <a href="https://t.me/OpenLongevity" target="_blank" rel="noopener noreferrer" className={styles.partnerLink}>(Telegram)</a>
                            <span className={styles.partnersSep}>и</span>
                            <a href="https://scienceagainstaging.com" target="_blank" rel="noopener noreferrer" className={styles.partnerLink}>Фондом «Наука за продление жизни»</a>
                        </div>
                    </div>
                    <div className={styles.heroWarning}>
                        <div className={styles.heroWarningIcon}>⚠️</div>
                        <p>
                            <strong>Внимание!</strong> Проект в очень ранней стадии разработки, работоспособность и сохранность данных не гарантированы.
                            Все заявления на этом лендинге носят демонстрационный характер и не все соответствуют реальности.
                            Терапий для РПЖ сейчас (на 2026.03.10) не существует.
                            За любыми вопросами здоровья обращайтесь к врачу — квалифицированному специалисту.
                        </p>
                    </div>
                </section>

                <section className={styles.links}>
                    <div className={styles.sectionInner}>
                        <div className={styles.linksGrid}>
                            {LINKS_GRID.map(({ href, icon, color, label, desc }) => (
                                <a key={href} href={href} target="_blank" rel="noopener noreferrer" className={styles.linkCard}>
                                    <div className={styles.linkIcon} style={{ background: color }}>{icon}</div>
                                    <div>
                                        <div className={styles.linkLabel}>{label}</div>
                                        <div className={styles.linkDesc}>{desc}</div>
                                    </div>
                                </a>
                            ))}
                        </div>
                    </div>
                </section>

                <section className={styles.about} id="about">
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                            <h2 className={styles.sectionTitle}>Что такое Карта Знаний?</h2>
                            <p className={styles.sectionSubtitle}>
                                Не просто база данных — живая экосистема, преобразующая хаос научной информации
                                в структурированный путь к долголетию.
                            </p>
                        </div>
                        <div className={styles.aboutGrid}>
                            <div className={`${styles.aboutCard} ${styles.aboutCardBlue}`}>
                                <div className={`${styles.aboutIcon} ${styles.aboutIconBlue}`}>⬡</div>
                                <h3>Направленный граф (DAG)</h3>
                                <p>Directed Acyclic Graph — от фундаментальной и системной биологии и генетики до сложнейших регенеративных терапий и наномедицины. Цепочки и пути: наглядное понимание того, как одно открытие приближает создание терапий от возраст-зависимых заболеваний.</p>
                            </div>
                            <div className={`${styles.aboutCard} ${styles.aboutCardPurple}`}>
                                <div className={`${styles.aboutIcon} ${styles.aboutIconPurple}`}>🤖</div>
                                <h3>Автоматизированный ИИ-учёный</h3>
                                <p>Анализирует массив данных, недоступный человеку. Быстрый анализ и синтез — обзор тысяч публикаций ежедневно. Предсказание открытий — алгоритмы указывают на наиболее перспективные точки приложения усилий. Находит закономерности и паттерны, скрытые от человеческого глаза.</p>
                            </div>
                            <div className={`${styles.aboutCard} ${styles.aboutCardPink}`}>
                                <div className={`${styles.aboutIcon} ${styles.aboutIconPink}`}>🌐</div>
                                <h3>Открыто и бесплатно</h3>
                                <p>Проект открыт и бесплатен для всех — от идей до исходного кода. Кардинально ускорить науку можно только совместными усилиями, без барьеров к инструментам и знаниям.</p>
                            </div>
                        </div>
                    </div>
                </section>

                <section className={styles.progress}>
                    <div className={styles.sectionInner}>
                        <div className={styles.progressGrid}>
                            <div className={styles.progressCard}>
                                <h2>Мониторинг прогресса науки</h2>
                                <p>Отслеживайте текущий статус разработки каждой технологии: от идей и гипотез до клинических испытаний и практического использования. Карта показывает прогресс в главной задаче и наиболее перспективных отраслях долголетия.</p>
                                <div className={styles.progressBars}>
                                    {PROGRESS_BARS.map(({ label, pct }) => (
                                        <div key={label} className={styles.barRow}>
                                            <span>{label}</span>
                                            <div className={styles.barTrack}>
                                                <div className={styles.barFill} style={{ width: `${pct}%` }} />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                            <div className={styles.collab}>
                                <h2>Коллаборативное решение задач</h2>
                                <p>Социальная сеть для учёных и всех интересующихся. Добавляйте блоки знаний, создавайте связи, работайте совместно над структурированием пути к долголетию. Наука ускоряется, когда люди думают вместе.</p>
                                <div className={styles.collabItems}>
                                    {COLLAB_ITEMS.map(item => (
                                        <div key={item} className={styles.collabItem}>{item}</div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                <section className={styles.features} id="features">
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                            <h2 className={styles.sectionTitle}>Реализованная функциональность</h2>
                            <div className={styles.titleBar} />
                        </div>
                        <div className={styles.featuresGrid}>
                            {FEATURES_GRID.map(({ color, icon, title, desc }) => (
                                <div key={title} className={styles.featureCard}>
                                    <div className={styles.featureIcon} style={{ color }}>{icon}</div>
                                    <h4>{title}</h4>
                                    <p>{desc}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                <section className={styles.future}>
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                            <div className={styles.futureBadge}>В разработке</div>
                            <h2 className={`${styles.sectionTitle} ${styles.sectionTitleLight}`}>Будущая функциональность</h2>
                        </div>
                        <div className={styles.futureGrid}>
                            {FUTURE_GRID.map(({ title, desc }) => (
                                <div key={title} className={styles.futureCard}>
                                    <h4>{title}</h4>
                                    <p>{desc}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                <section className={styles.cta} id="contribute">
                    <div className={styles.ctaInner}>
                        <h2>Проект открыт и<br />бесплатен для всех</h2>
                        <p>Мы верим, что победа над старением — это общая задача человечества. Присоединяйтесь как исследователь, разработчик или спонсор.</p>
                        <div className={styles.ctaButtons}>
                            <a href="https://t.me/KnowledgeMapForum" target="_blank" rel="noopener noreferrer" className={styles.ctaWhiteBtn}>Стать участником</a>
                            <a href="https://t.me/KnowledgeMapForum/1079/1080" target="_blank" rel="noopener noreferrer" className={styles.ctaGhostBtn}>Поддержать проект</a>
                        </div>
                    </div>
                </section>

                <section className={styles.contribute}>
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                            <h2 className={styles.sectionTitle}>Как внести свой вклад</h2>
                        </div>
                        <div className={styles.contributeGrid}>
                            {CONTRIBUTE_GRID.map(({ icon, title, desc, href, linkText }) => (
                                <div key={title} className={styles.contributeCard}>
                                    <div className={styles.contributeIcon}>{icon}</div>
                                    <h4>{title}</h4>
                                    <p>{desc}</p>
                                    <a href={href} target="_blank" rel="noopener noreferrer" className={styles.contributeLink}>{linkText} →</a>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                <section className={styles.education} id="education">
                    <div className={styles.sectionInner}>
                        <div className={styles.educationGrid}>
                            <div className={styles.educationContent}>
                                <div className={styles.educationBadge}>Бесплатное обучение</div>
                                <h2>Хотите внести вклад в науку о долголетии?</h2>
                                <p>Для участия в Карте Знаний и РПЖ не нужна предварительная подготовка — учитесь прямо здесь. Система интервального повторения и активной обратной связи встроена прямо в Карту Знаний. <strong>Становись умнее в выбранной области знаний!</strong></p>
                                <ul className={styles.educationList}>
                                    {EDUCATION_LIST.map(item => <li key={item}>{item}</li>)}
                                </ul>
                            </div>
                            <div className={styles.educationVisual}>
                                <div className={styles.flashcard}>
                                    <div className={styles.flashcardLabel}>Интервальное повторение</div>
                                    <div className={styles.flashcardQ}>Что такое теломера?</div>
                                    <div className={styles.flashcardA}>Концевой участок хромосомы, защищающий её от деградации. Укорачивается при каждом делении клетки.</div>
                                    <div className={styles.flashcardBtns}>
                                        <span>Снова</span>
                                        <span>Хорошо</span>
                                        <span>Легко</span>
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
                                <div className={styles.sayforeverBadge}>Say Forever</div>
                                <h2>Ежемесячная акция SayForever</h2>
                                <p>В первую субботу каждого месяца — социологический опрос:</p>
                                <ul className={styles.sayforeverList}>
                                    <li>Сколько лет вы хотели бы жить?</li>
                                    <li>Насколько это для вас важно?</li>
                                    <li>Как много вы готовы сделать для продления жизни?</li>
                                </ul>
                                <p className={styles.sayforeverSelf}>Такую акцию вы можете провести самостоятельно!</p>
                                <a href="https://sayforever.org/" target="_blank" rel="noopener noreferrer" className={styles.sayforeverLink}>sayforever.org →</a>
                            </div>
                        </div>
                    </div>
                </section>

                <section className={styles.author}>
                    <div className={styles.sectionInner}>
                        <div className={styles.authorInner}>
                            <div className={styles.authorAvatar}>ДП</div>
                            <h3>Дима Прокофьев</h3>
                            <div className={styles.authorRole}>Основатель и главный разработчик</div>
                            <blockquote className={styles.authorQuote}>
                                «Всю жизнь, сколько себя помню, мечтал о том, чтобы каждый смог жить столько, сколько сам захочет, лучшей жизнью. Карта Знаний — это попытка воплотить мечту в реальность.»
                            </blockquote>
                            <a href="https://t.me/dima_prokofev" target="_blank" rel="noopener noreferrer" className={styles.authorTg}>Telegram: @dima_prokofev</a>
                        </div>
                    </div>
                </section>

                <section className={styles.finalCta}>
                    <a href="https://t.me/KnowledgeMapForum" target="_blank" rel="noopener noreferrer" className={styles.finalCtaBtn}>
                        Присоединяйтесь к сообществу →
                    </a>
                </section>

            </main>
        </div>
    );
};

export default LandingUI;
