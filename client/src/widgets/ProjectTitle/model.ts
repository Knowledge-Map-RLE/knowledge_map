export interface ProjectTitleLink {
    to: string;
    translationKey: string;
}

export const SLOGAN_KEYS = [
    'header.project.slogans.0',
    'header.project.slogans.1',
    'header.project.slogans.2',
] as const;

export const LINKS: readonly ProjectTitleLink[] = [
    { to: '/', translationKey: 'header.project.navigation.landing' },
    { to: '/introduction', translationKey: 'header.project.navigation.introduction' },
    { to: '/km', translationKey: 'header.project.navigation.knowledgeMap' },
    { to: '/rle_databases', translationKey: 'header.project.navigation.rleDatabases' },
    { to: '/data_download', translationKey: 'header.project.navigation.dataDownload' },
    { to: '/data_extraction', translationKey: 'header.project.navigation.dataExtraction' },
    { to: '/science_articles', translationKey: 'header.project.navigation.scienceArticles' },
    { to: '/pattern_analysis', translationKey: 'header.project.navigation.patternAnalysis' },
    { to: '/pattern_editor', translationKey: 'header.project.navigation.patternEditor' },
    { to: '/pattern_miner', translationKey: 'header.project.navigation.patternMiner' },
    { to: '/article_editor', translationKey: 'header.project.navigation.articleEditor' },
    { to: '/social_network', translationKey: 'header.project.navigation.socialNetwork' },
    { to: '/subscription', translationKey: 'header.project.navigation.subscription' },
] as const;

export interface ProjectTitleProps {
    className?: string;
}
