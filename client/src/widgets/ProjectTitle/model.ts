export interface ProjectTitleLink {
    to: string;
    label: string;
}

export const SLOGANS = [
    'В БЕКОНЕЧНОСТЬ И ЕЩЁ ДАЛЬШЕ!',
    'ЗНАНИЯ — ЖИЗНЬ!',
    '∞ не lim',
] as const;

export const LINKS: readonly ProjectTitleLink[] = [
    { to: '/', label: 'Главная — Лендинг' },
    { to: '/introduction', label: 'Введение' },
    { to: '/km', label: 'Карта знаний' },
    { to: '/rle_databases', label: 'Базы данных РПЖ' },
    { to: '/data_download', label: 'Загрузка данных' },
    { to: '/data_extraction', label: 'Извлечение данных' },
    { to: '/science_articles', label: 'Карта научных статей' },
    { to: '/pattern_analysis', label: 'Анализ паттернов' },
    { to: '/pattern_editor', label: 'Проверка уникальности знаний' },
    { to: '/pattern_miner', label: 'Паттерны графа утверждений' },
    { to: '/article_editor', label: 'Редактор статей' },
    { to: '/social_network', label: 'Социальная сеть' },
    { to: '/subscription', label: 'Подписка' },
] as const;

export interface ProjectTitleProps {
    className?: string;
}
