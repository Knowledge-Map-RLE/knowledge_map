export interface LinkCard {
    href: string;
    icon: string;
    color: string;
    translationPath: string;
}

export interface FeatureCard {
    color: string;
    icon: string;
    translationPath: string;
}

export interface FutureCard {
    translationPath: string;
}

export interface ProgressBar {
    translationKey: string;
    pct: number;
}

export interface ContributeCard {
    icon: string;
    translationPath: string;
    href: string;
}

export const LINKS_GRID: readonly LinkCard[] = [
    { href: 'https://t.me/KnowledgeMapForum', icon: 'ФМ', color: '#6366F1', translationPath: 'landing.links.forum' },
    { href: 'https://miro.com/app/board/uXjVPyIT5F0=/?moveToWidget=3458764562951665022&cot=14', icon: 'КЗ', color: '#A855F7', translationPath: 'landing.links.miro' },
    { href: 'https://github.com/Knowledge-Map-RLE/knowledge_map', icon: 'GH', color: '#1E293B', translationPath: 'landing.links.github' },
    { href: 'https://docs.google.com/presentation/d/1hfJCNQJeCMqPmXxc6VFiH4hm6oR8f7Gi5o-m8iXBczc/edit?slide=id.p#slide=id.p', icon: 'PR', color: '#0EA5E9', translationPath: 'landing.links.presentation' },
    { href: 'https://t.me/KnowledgeMapForum/800/5760', icon: '▶', color: '#EC4899', translationPath: 'landing.links.video' },
    { href: 'https://t.me/KnowledgeMapForum/1079/1080', icon: '♥', color: '#F59E0B', translationPath: 'landing.links.donations' },
] as const;

export const FEATURES_GRID: readonly FeatureCard[] = [
    { color: '#6366F1', icon: '⬡', translationPath: 'landing.features.graph' },
    { color: '#A855F7', icon: '📄', translationPath: 'landing.features.articles' },
    { color: '#EC4899', icon: '🔬', translationPath: 'landing.features.annotations' },
    { color: '#0EA5E9', icon: '🔗', translationPath: 'landing.features.patternMining' },
    { color: '#10B981', icon: '🗄️', translationPath: 'landing.features.literature' },
    { color: '#F59E0B', icon: '⚡', translationPath: 'landing.features.layoutEngine' },
    { color: '#8B5CF6', icon: '🔐', translationPath: 'landing.features.authentication' },
    { color: '#1E293B', icon: '📊', translationPath: 'landing.features.dataExtraction' },
] as const;

export const FUTURE_GRID: readonly FutureCard[] = [
    { translationPath: 'landing.future.aiScientist' },
    { translationPath: 'landing.future.knowledgeGraph' },
    { translationPath: 'landing.future.ontologies' },
    { translationPath: 'landing.future.researchNetwork' },
    { translationPath: 'landing.future.education' },
    { translationPath: 'landing.future.integration' },
] as const;

export const PROGRESS_BARS: readonly ProgressBar[] = [
    { translationKey: 'landing.progress.senolytics', pct: 55 },
    { translationKey: 'landing.progress.geneTherapy', pct: 38 },
    { translationKey: 'landing.progress.nanomedicine', pct: 18 },
] as const;

export const COLLAB_ITEMS = [
    'landing.collaboration.editGraph',
    'landing.collaboration.connectConcepts',
    'landing.collaboration.verifyData',
    'landing.collaboration.contributions',
] as const;

export const CONTRIBUTE_GRID: readonly ContributeCard[] = [
    { icon: '💬', translationPath: 'landing.contribute.community', href: 'https://t.me/KnowledgeMapForum' },
    { icon: '🗣️', translationPath: 'landing.contribute.discuss', href: 'https://t.me/KnowledgeMapForum' },
    { icon: '💻', translationPath: 'landing.contribute.researcher', href: 'https://github.com/Knowledge-Map-RLE/knowledge_map' },
    { icon: '❤️', translationPath: 'landing.contribute.sponsor', href: 'https://t.me/KnowledgeMapForum/1079/1080' },
] as const;

export const EDUCATION_LIST = [
    'landing.education.topics.programming',
    'landing.education.topics.dataScience',
    'landing.education.topics.graphs',
    'landing.education.topics.devops',
    'landing.education.topics.biology',
    'landing.education.topics.genetics',
] as const;
