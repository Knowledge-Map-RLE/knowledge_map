import Header from '../Header';
import Site_map from '../Site_map';
import s from './Landing.module.css';

export default function Landing() {
  return (
    <div className={s.page}>
      <Header showSearch={true} className={s.header} />
      <main className={s.main}>

        {/* ── 1. HERO ─────────────────────────────────────────── */}
        <section className={s.hero}>
          <div className={s.heroGlowBlue} />
          <div className={s.heroGlowPurple} />
          <div className={s.heroInner}>
            <div className={s.heroBadge}>Open Science Initiative</div>
            <h1 className={s.heroTitle}>
              Победить старение.<br />
              <span className={s.heroGradientText}>Жить, сколько хочешь.</span>
            </h1>
            <p className={s.heroSubtitle}>
              Карта Знаний — технологическая карта достижения радикального продления жизни человека (РПЖ).
              Автоматизированный ИИ-учёный, соединяющий науку, данные и человека.
            </p>
            <div className={s.heroCta}>
              <a
                href="https://t.me/KnowledgeMapForum"
                target="_blank"
                rel="noopener noreferrer"
                className={s.ctaBtnPrimary}
              >
                Присоединиться
              </a>
              <a
                href="https://miro.com/app/board/uXjVPyIT5F0=/?moveToWidget=3458764562951665022&cot=14"
                target="_blank"
                rel="noopener noreferrer"
                className={s.ctaBtnSecondary}
              >
                Посмотреть карту
              </a>
            </div>
            <div className={s.partners}>
              <span className={s.partnersLabel}>Совместно с:</span>
              <a href="https://openlongevity.org/" target="_blank" rel="noopener noreferrer" className={s.partnerLink}>
                Open Longevity
              </a>
              <a href="https://t.me/OpenLongevity" target="_blank" rel="noopener noreferrer" className={s.partnerLink}>
                (Telegram)
              </a>
              <span className={s.partnersSep}>и</span>
              <a href="https://scienceagainstaging.com" target="_blank" rel="noopener noreferrer" className={s.partnerLink}>
                Фондом «Наука за продление жизни»
              </a>
            </div>
          </div>
          <div className={s.heroWarning}>
            <div className={s.heroWarningIcon}>⚠️</div>
            <p>
              <strong>Внимание!</strong> Проект в очень ранней стадии разработки, работоспособность и сохранность данных не гарантированы.
              Все заявления на этом лендинге носят демонстрационный характер и не все соответствуют реальности.
              Терапий для РПЖ сейчас (на 2026.03.10) не существует.
              За любыми вопросами здоровья обращайтесь к врачу — квалифицированному специалисту.
            </p>
          </div>
        </section>

        {/* ── 2. БЫСТРЫЕ ССЫЛКИ ───────────────────────────────── */}
        <section className={s.links}>
          <div className={s.sectionInner}>
            <div className={s.linksGrid}>
              {[
                { href: 'https://t.me/KnowledgeMapForum', icon: 'ФМ', color: '#6366F1', label: 'Форум', desc: 'Сообщество единомышленников, общение, новости разработки' },
                { href: 'https://miro.com/app/board/uXjVPyIT5F0=/?moveToWidget=3458764562951665022&cot=14', icon: 'КЗ', color: '#A855F7', label: 'Карта (Miro)', desc: 'Демо: 3000 блоков и 3000 связей, созданных вручную' },
                { href: 'https://github.com/Knowledge-Map-RLE/knowledge_map', icon: 'GH', color: '#1E293B', label: 'GitHub', desc: 'Исходный код — приходите вносить вклад' },
                { href: 'https://docs.google.com/presentation/d/1hfJCNQJeCMqPmXxc6VFiH4hm6oR8f7Gi5o-m8iXBczc/edit?slide=id.p#slide=id.p', icon: 'PR', color: '#0EA5E9', label: 'Презентация', desc: 'Основные идеи проекта' },
                { href: 'https://t.me/KnowledgeMapForum/800/5760', icon: '▶', color: '#EC4899', label: 'Видео 10 часов', desc: 'Для самых стойких — всё о Карте Знаний' },
                { href: 'https://t.me/KnowledgeMapForum/1079/1080', icon: '♥', color: '#F59E0B', label: 'Донаты', desc: 'Поддержать проект финансово' },
              ].map(({ href, icon, color, label, desc }) => (
                <a key={href} href={href} target="_blank" rel="noopener noreferrer" className={s.linkCard}>
                  <div className={s.linkIcon} style={{ background: color }}>{icon}</div>
                  <div>
                    <div className={s.linkLabel}>{label}</div>
                    <div className={s.linkDesc}>{desc}</div>
                  </div>
                </a>
              ))}
            </div>
          </div>
        </section>

        {/* ── 3. ЧТО ТАКОЕ КАРТА ЗНАНИЙ? ─────────────────────── */}
        <section className={s.about} id="about">
          <div className={s.sectionInner}>
            <div className={s.sectionHeader}>
              <h2 className={s.sectionTitle}>Что такое Карта Знаний?</h2>
              <p className={s.sectionSubtitle}>
                Не просто база данных — живая экосистема, преобразующая хаос научной информации
                в структурированный путь к долголетию.
              </p>
            </div>
            <div className={s.aboutGrid}>
              <div className={`${s.aboutCard} ${s.aboutCardBlue}`}>
                <div className={`${s.aboutIcon} ${s.aboutIconBlue}`}>⬡</div>
                <h3>Направленный граф (DAG)</h3>
                <p>
                  Directed Acyclic Graph — от фундаментальной и системной биологии и генетики
                  до сложнейших регенеративных терапий и наномедицины. Цепочки и пути:
                  наглядное понимание того, как одно открытие приближает создание терапий
                  от возраст-зависимых заболеваний.
                </p>
              </div>
              <div className={`${s.aboutCard} ${s.aboutCardPurple}`}>
                <div className={`${s.aboutIcon} ${s.aboutIconPurple}`}>🤖</div>
                <h3>Автоматизированный ИИ-учёный</h3>
                <p>
                  Анализирует массив данных, недоступный человеку. Быстрый анализ и синтез —
                  обзор тысяч публикаций ежедневно. Предсказание открытий — алгоритмы указывают
                  на наиболее перспективные точки приложения усилий. Находит закономерности
                  и паттерны, скрытые от человеческого глаза.
                </p>
              </div>
              <div className={`${s.aboutCard} ${s.aboutCardPink}`}>
                <div className={`${s.aboutIcon} ${s.aboutIconPink}`}>🌐</div>
                <h3>Открыто и бесплатно</h3>
                <p>
                  Проект открыт и бесплатен для всех — от идей до исходного кода.
                  Кардинально ускорить науку можно только совместными усилиями,
                  без барьеров к инструментам и знаниям.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ── 4. ПРОГРЕСС + КОЛЛАБОРАЦИЯ ──────────────────────── */}
        <section className={s.progress}>
          <div className={s.sectionInner}>
            <div className={s.progressGrid}>
              <div className={s.progressCard}>
                <h2>Мониторинг прогресса науки</h2>
                <p>
                  Отслеживайте текущий статус разработки каждой технологии:
                  от идей и гипотез до клинических испытаний и практического использования.
                  Карта показывает прогресс в главной задаче и наиболее перспективных отраслях долголетия.
                </p>
                <div className={s.progressBars}>
                  {[
                    { label: 'Сенолитики', pct: 55 },
                    { label: 'Генная терапия', pct: 38 },
                    { label: 'Наномедицина', pct: 18 },
                  ].map(({ label, pct }) => (
                    <div key={label} className={s.barRow}>
                      <span>{label}</span>
                      <div className={s.barTrack}>
                        <div className={s.barFill} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className={s.collab}>
                <h2>Коллаборативное решение задач</h2>
                <p>
                  Социальная сеть для учёных и всех интересующихся.
                  Добавляйте блоки знаний, создавайте связи, работайте совместно
                  над структурированием пути к долголетию.
                  Наука ускоряется, когда люди думают вместе.
                </p>
                <div className={s.collabItems}>
                  <div className={s.collabItem}>📝 Совместное редактирование графа знаний</div>
                  <div className={s.collabItem}>🔗 Создание связей между концепциями</div>
                  <div className={s.collabItem}>💬 Обсуждение и верификация данных</div>
                  <div className={s.collabItem}>🏆 Система контрибуций и рейтинга</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── 5. РЕАЛИЗОВАННАЯ ФУНКЦИОНАЛЬНОСТЬ ───────────────── */}
        <section className={s.features} id="features">
          <div className={s.sectionInner}>
            <div className={s.sectionHeader}>
              <h2 className={s.sectionTitle}>Реализованная функциональность</h2>
              <div className={s.titleBar} />
            </div>
            <div className={s.featuresGrid}>
              {[
                {
                  color: '#6366F1',
                  icon: '⬡',
                  title: 'Интерактивный граф',
                  desc: 'Визуализация на Pixi.js с GPU-ускорением. Создание, редактирование и удаление блоков и связей. Клавиатурные горячие клавиши (Q/W/E), контекстное меню, иерархия уровней.',
                },
                {
                  color: '#A855F7',
                  icon: '📄',
                  title: 'Обработка статей',
                  desc: 'Загрузка PDF drag-and-drop, конвертация в Markdown. Интеграция с PubMed и PMC. Рендеринг формул (KaTeX), таблиц. Движки Marker и HURIDOCS.',
                },
                {
                  color: '#EC4899',
                  icon: '🔬',
                  title: 'NLP и аннотации',
                  desc: '94+ типа аннотаций: части речи, синтаксис, именованные сущности. 10 научных типов: болезнь, терапия, ген, белок. Ручная и автоматическая аннотация через spaCy.',
                },
                {
                  color: '#0EA5E9',
                  icon: '🔗',
                  title: 'Добыча паттернов',
                  desc: 'Генерация паттернов из аннотаций с SSE-стримингом. Построение и визуализация цепочек действий из текста.',
                },
                {
                  color: '#10B981',
                  icon: '🗄️',
                  title: 'База научной литературы',
                  desc: 'ETL-пайплайн: миллионы статей PubMed в Neo4j. Граф цитирований. Полные тексты PubMed Central Open Access.',
                },
                {
                  color: '#F59E0B',
                  icon: '⚡',
                  title: 'Движок укладки (Rust)',
                  desc: 'SIMD-оптимизация — в 9× быстрее Python-версии. Топологическая сортировка с параллелизмом (Rayon). gRPC API для стриминга.',
                },
                {
                  color: '#8B5CF6',
                  icon: '🔐',
                  title: 'Аутентификация',
                  desc: 'Регистрация, вход, двухфакторная аутентификация (2FA), восстановление пароля, CAPTCHA.',
                },
                {
                  color: '#1E293B',
                  icon: '📊',
                  title: 'Извлечение данных',
                  desc: 'Просмотр оригинального PDF и Markdown бок о бок. Вкладки аннотаций, связей, паттернов, цепочек — весь пайплайн в одном интерфейсе.',
                },
              ].map(({ color, icon, title, desc }) => (
                <div key={title} className={s.featureCard}>
                  <div className={s.featureIcon} style={{ color }}>{icon}</div>
                  <h4>{title}</h4>
                  <p>{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── 6. БУДУЩАЯ ФУНКЦИОНАЛЬНОСТЬ ─────────────────────── */}
        <section className={s.future}>
          <div className={s.sectionInner}>
            <div className={s.sectionHeader}>
              <div className={s.futureBadge}>В разработке</div>
              <h2 className={`${s.sectionTitle} ${s.sectionTitleLight}`}>Будущая функциональность</h2>
            </div>
            <div className={s.futureGrid}>
              {[
                {
                  title: 'Генеративный ИИ-учёный',
                  desc: 'Самостоятельно синтезирует и проверяет гипотезы, ставя задачу для ручного или автоматизированного исполнения. Предсказывает открытия — алгоритмы указывают на наиболее перспективные точки.',
                },
                {
                  title: 'Расширенный граф знаний',
                  desc: 'Перенос данных из Miro-демонстрации (3000 блоков, 3000 связей) в систему. Шаблоны структур. Совместное редактирование в реальном времени.',
                },
                {
                  title: 'Онтологии и семантика',
                  desc: 'Автогенерация семантических онтологий из аннотаций. GraphQL API для сложных запросов. Связывание сущностей с UniProt, OMIM, ChEMBL.',
                },
                {
                  title: 'Социальная сеть учёных',
                  desc: 'Профили исследователей, коллаборативные рабочие пространства, система задач, контрибуций и экспертных рецензий.',
                },
                {
                  title: 'Образовательный модуль',
                  desc: 'Система интервального повторения и активной обратной связи, встроенная в Карту Знаний. Персонализированные пути обучения.',
                },
                {
                  title: 'Глобальная интеграция',
                  desc: 'Синхронизация с PubMed, bioRxiv, arXiv и другими мировыми хранилищами в режиме реального времени.',
                },
              ].map(({ title, desc }) => (
                <div key={title} className={s.futureCard}>
                  <h4>{title}</h4>
                  <p>{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── 7. CTA — ОТКРЫТОСТЬ ─────────────────────────────── */}
        <section className={s.cta} id="contribute">
          <div className={s.ctaInner}>
            <h2>Проект открыт и<br />бесплатен для всех</h2>
            <p>
              Мы верим, что победа над старением — это общая задача человечества.
              Присоединяйтесь как исследователь, разработчик или спонсор.
            </p>
            <div className={s.ctaButtons}>
              <a
                href="https://t.me/KnowledgeMapForum"
                target="_blank"
                rel="noopener noreferrer"
                className={s.ctaWhiteBtn}
              >
                Стать участником
              </a>
              <a
                href="https://t.me/KnowledgeMapForum/1079/1080"
                target="_blank"
                rel="noopener noreferrer"
                className={s.ctaGhostBtn}
              >
                Поддержать проект
              </a>
            </div>
          </div>
        </section>

        {/* ── 8. КАК ВНЕСТИ ВКЛАД ─────────────────────────────── */}
        <section className={s.contribute}>
          <div className={s.sectionInner}>
            <div className={s.sectionHeader}>
              <h2 className={s.sectionTitle}>Как внести свой вклад</h2>
            </div>
            <div className={s.contributeGrid}>
              {[
                { icon: '💬', title: 'Быть в сообществе', desc: 'Вступайте в форум, следите за новостями разработки, будьте в курсе событий.', href: 'https://t.me/KnowledgeMapForum', linkText: 'Перейти в форум' },
                { icon: '🗣️', title: 'Обсуждать', desc: 'Делитесь идеями, задавайте вопросы, предлагайте улучшения на форуме.', href: 'https://t.me/KnowledgeMapForum', linkText: 'Начать обсуждение' },
                { icon: '💻', title: 'Исследователь или разработчик', desc: 'Присоединяйтесь через GitHub, вносите код или научные знания.', href: 'https://github.com/Knowledge-Map-RLE/knowledge_map', linkText: 'Открыть репозиторий' },
                { icon: '❤️', title: 'Спонсор', desc: 'Поддержите Карту Знаний финансово — реквизиты по ссылке.', href: 'https://t.me/KnowledgeMapForum/1079/1080', linkText: 'Реквизиты донатов' },
              ].map(({ icon, title, desc, href, linkText }) => (
                <div key={title} className={s.contributeCard}>
                  <div className={s.contributeIcon}>{icon}</div>
                  <h4>{title}</h4>
                  <p>{desc}</p>
                  <a href={href} target="_blank" rel="noopener noreferrer" className={s.contributeLink}>
                    {linkText} →
                  </a>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── 9. БЕСПЛАТНОЕ ОБРАЗОВАНИЕ ───────────────────────── */}
        <section className={s.education} id="education">
          <div className={s.sectionInner}>
            <div className={s.educationGrid}>
              <div className={s.educationContent}>
                <div className={s.educationBadge}>Бесплатное обучение</div>
                <h2>Хотите внести вклад в науку о долголетии?</h2>
                <p>
                  Для участия в Карте Знаний и РПЖ не нужна предварительная подготовка —
                  учитесь прямо здесь. Система интервального повторения и активной обратной связи
                  встроена прямо в Карту Знаний. <strong>Становись умнее в выбранной области знаний!</strong>
                </p>
                <ul className={s.educationList}>
                  <li>🐍 Python и R — языки научного анализа</li>
                  <li>📊 Data Science и анализ данных</li>
                  <li>🕸️ Графы и их визуализация</li>
                  <li>🚀 DevOps и CI/CD</li>
                  <li>🧬 Биология: фундаментальная, молекулярная, системная</li>
                  <li>🧪 Популяционная генетика, геномика, геронтология, биоинформатика</li>
                </ul>
              </div>
              <div className={s.educationVisual}>
                <div className={s.flashcard}>
                  <div className={s.flashcardLabel}>Интервальное повторение</div>
                  <div className={s.flashcardQ}>Что такое теломера?</div>
                  <div className={s.flashcardA}>
                    Концевой участок хромосомы, защищающий её от деградации.
                    Укорачивается при каждом делении клетки.
                  </div>
                  <div className={s.flashcardBtns}>
                    <span>Снова</span>
                    <span>Хорошо</span>
                    <span>Легко</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── 10. SAYFOREVER ──────────────────────────────────── */}
        <section className={s.sayforever}>
          <div className={s.sectionInner}>
            <div className={s.sayforeverInner}>
              <div className={s.sayforeverContent}>
                <div className={s.sayforeverBadge}>Say Forever</div>
                <h2>Ежемесячная акция SayForever</h2>
                <p>В первую субботу каждого месяца — социологический опрос:</p>
                <ul className={s.sayforeverList}>
                  <li>Сколько лет вы хотели бы жить?</li>
                  <li>Насколько это для вас важно?</li>
                  <li>Как много вы готовы сделать для продления жизни?</li>
                </ul>
                <p className={s.sayforeverSelf}>Такую акцию вы можете провести самостоятельно!</p>
                <a
                  href="https://sayforever.org/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className={s.sayforeverLink}
                >
                  sayforever.org →
                </a>
              </div>
            </div>
          </div>
        </section>

        {/* ── 11. АВТОР ───────────────────────────────────────── */}
        <section className={s.author}>
          <div className={s.sectionInner}>
            <div className={s.authorInner}>
              <div className={s.authorAvatar}>ДП</div>
              <h3>Дима Прокофьев</h3>
              <div className={s.authorRole}>Основатель и главный разработчик</div>
              <blockquote className={s.authorQuote}>
                «Всю жизнь, сколько себя помню, мечтал о том, чтобы каждый смог жить столько,
                сколько сам захочет, лучшей жизнью. Карта Знаний — это попытка воплотить мечту в реальность.»
              </blockquote>
              <a
                href="https://t.me/dima_prokofev"
                target="_blank"
                rel="noopener noreferrer"
                className={s.authorTg}
              >
                Telegram: @dima_prokofev
              </a>
            </div>
          </div>
        </section>

        {/* ── 12. ФИНАЛЬНЫЙ CTA ───────────────────────────────── */}
        <section className={s.finalCta}>
          <a
            href="https://t.me/KnowledgeMapForum"
            target="_blank"
            rel="noopener noreferrer"
            className={s.finalCtaBtn}
          >
            Присоединяйтесь к сообществу →
          </a>
        </section>

      </main>

      <footer className={s.footer}>
        <Site_map />
      </footer>
    </div>
  );
}
