export interface LinkCard {
    href: string;
    icon: string;
    color: string;
    label: string;
    desc: string;
}

export interface FeatureCard {
    color: string;
    icon: string;
    title: string;
    desc: string;
}

export interface FutureCard {
    title: string;
    desc: string;
}

export interface ProgressBar {
    label: string;
    pct: number;
}

export interface ContributeCard {
    icon: string;
    title: string;
    desc: string;
    href: string;
    linkText: string;
}

export const LINKS_GRID: readonly LinkCard[] = [
    { href: 'https://t.me/KnowledgeMapForum', icon: 'ФМ', color: '#6366F1', label: 'Форум', desc: 'Сообщество единомышленников, общение, новости разработки' },
    { href: 'https://miro.com/app/board/uXjVPyIT5F0=/?moveToWidget=3458764562951665022&cot=14', icon: 'КЗ', color: '#A855F7', label: 'Карта (Miro)', desc: 'Демо: 3000 блоков и 3000 связей, созданных вручную' },
    { href: 'https://github.com/Knowledge-Map-RLE/knowledge_map', icon: 'GH', color: '#1E293B', label: 'GitHub', desc: 'Исходный код — приходите вносить вклад' },
    { href: 'https://docs.google.com/presentation/d/1hfJCNQJeCMqPmXxc6VFiH4hm6oR8f7Gi5o-m8iXBczc/edit?slide=id.p#slide=id.p', icon: 'PR', color: '#0EA5E9', label: 'Презентация', desc: 'Основные идеи проекта' },
    { href: 'https://t.me/KnowledgeMapForum/800/5760', icon: '▶', color: '#EC4899', label: 'Видео 10 часов', desc: 'Для самых стойких — всё о Карте Знаний' },
    { href: 'https://t.me/KnowledgeMapForum/1079/1080', icon: '♥', color: '#F59E0B', label: 'Донаты', desc: 'Поддержать проект финансово' },
] as const;

export const FEATURES_GRID: readonly FeatureCard[] = [
    { color: '#6366F1', icon: '⬡', title: 'Интерактивный граф', desc: 'Визуализация на Pixi.js с GPU-ускорением. Создание, редактирование и удаление блоков и связей. Клавиатурные горячие клавиши (Q/W/E), контекстное меню, иерархия уровней.' },
    { color: '#A855F7', icon: '📄', title: 'Обработка статей', desc: 'Загрузка PDF drag-and-drop, конвертация в Markdown. Интеграция с PubMed и PMC. Рендеринг формул (KaTeX), таблиц. Движки Marker и HURIDOCS.' },
    { color: '#EC4899', icon: '🔬', title: 'NLP и аннотации', desc: '94+ типа аннотаций: части речи, синтаксис, именованные сущности. 10 научных типов: болезнь, терапия, ген, белок. Ручная и автоматическая аннотация через spaCy.' },
    { color: '#0EA5E9', icon: '🔗', title: 'Добыча паттернов', desc: 'Генерация паттернов из аннотаций с SSE-стримингом. Построение и визуализация цепочек действий из текста.' },
    { color: '#10B981', icon: '🗄️', title: 'База научной литературы', desc: 'ETL-пайплайн: миллионы статей PubMed в Neo4j. Граф цитирований. Полные тексты PubMed Central Open Access.' },
    { color: '#F59E0B', icon: '⚡', title: 'Движок укладки (Rust)', desc: 'SIMD-оптимизация — в 9× быстрее Python-версии. Топологическая сортировка с параллелизмом (Rayon). gRPC API для стриминга.' },
    { color: '#8B5CF6', icon: '🔐', title: 'Аутентификация', desc: 'Регистрация, вход, двухфакторная аутентификация (2FA), восстановление пароля, CAPTCHA.' },
    { color: '#1E293B', icon: '📊', title: 'Извлечение данных', desc: 'Просмотр оригинального PDF и Markdown бок о бок. Вкладки аннотаций, связей, паттернов, цепочек — весь пайплайн в одном интерфейсе.' },
] as const;

export const FUTURE_GRID: readonly FutureCard[] = [
    { title: 'Генеративный ИИ-учёный', desc: 'Самостоятельно синтезирует и проверяет гипотезы, ставя задачу для ручного или автоматизированного исполнения. Предсказывает открытия — алгоритмы указывают на наиболее перспективные точки.' },
    { title: 'Расширенный граф знаний', desc: 'Перенос данных из Miro-демонстрации (3000 блоков, 3000 связей) в систему. Шаблоны структур. Совместное редактирование в реальном времени.' },
    { title: 'Онтологии и семантика', desc: 'Автогенерация семантических онтологий из аннотаций. GraphQL API для сложных запросов. Связывание сущностей с UniProt, OMIM, ChEMBL.' },
    { title: 'Социальная сеть учёных', desc: 'Профили исследователей, коллаборативные рабочие пространства, система задач, контрибуций и экспертных рецензий.' },
    { title: 'Образовательный модуль', desc: 'Система интервального повторения и активной обратной связи, встроенная в Карту Знаний. Персонализированные пути обучения.' },
    { title: 'Глобальная интеграция', desc: 'Синхронизация с PubMed, bioRxiv, arXiv и другими мировыми хранилищами в режиме реального времени.' },
] as const;

export const PROGRESS_BARS: readonly ProgressBar[] = [
    { label: 'Сенолитики', pct: 55 },
    { label: 'Генная терапия', pct: 38 },
    { label: 'Наномедицина', pct: 18 },
] as const;

export const COLLAB_ITEMS: readonly string[] = [
    '📝 Совместное редактирование графа знаний',
    '🔗 Создание связей между концепциями',
    '💬 Обсуждение и верификация данных',
    '🏆 Система контрибуций и рейтинга',
] as const;

export const CONTRIBUTE_GRID: readonly ContributeCard[] = [
    { icon: '💬', title: 'Быть в сообществе', desc: 'Вступайте в форум, следите за новостями разработки, будьте в курсе событий.', href: 'https://t.me/KnowledgeMapForum', linkText: 'Перейти в форум' },
    { icon: '🗣️', title: 'Обсуждать', desc: 'Делитесь идеями, задавайте вопросы, предлагайте улучшения на форуме.', href: 'https://t.me/KnowledgeMapForum', linkText: 'Начать обсуждение' },
    { icon: '💻', title: 'Исследователь или разработчик', desc: 'Присоединяйтесь через GitHub, вносите код или научные знания.', href: 'https://github.com/Knowledge-Map-RLE/knowledge_map', linkText: 'Открыть репозиторий' },
    { icon: '❤️', title: 'Спонсор', desc: 'Поддержите Карту Знаний финансово — реквизиты по ссылке.', href: 'https://t.me/KnowledgeMapForum/1079/1080', linkText: 'Реквизиты донатов' },
] as const;

export const EDUCATION_LIST: readonly string[] = [
    '🐍 Python и R — языки научного анализа',
    '📊 Data Science и анализ данных',
    '🕸️ Графы и их визуализация',
    '🚀 DevOps и CI/CD',
    '🧬 Биология: фундаментальная, молекулярная, системная',
    '🧪 Популяционная генетика, геномика, геронтология, биоинформатика',
] as const;
