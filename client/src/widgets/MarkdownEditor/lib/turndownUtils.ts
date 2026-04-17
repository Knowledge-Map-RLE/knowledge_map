interface TurndownService {
    turndown(html: string): string;
}

interface TurndownOptions {
    headingStyle?: 'atx' | 'setext';
    codeBlockStyle?: 'fenced' | 'indented';
}

export const createTurndownService = (options: TurndownOptions = {}): TurndownService | null => {
    try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const mod = require('turndown');
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const TurndownServiceClass: any = mod.default || mod.TurndownService || mod;
        const td = new TurndownServiceClass({
            headingStyle: 'atx',
            codeBlockStyle: 'fenced',
            ...options,
        });

        td.addRule('preserveTables', {
            filter: 'table',
            replacement: function(content: string, node: HTMLElement) {
                return '\n' + node.outerHTML + '\n';
            }
        });

        return td;
    } catch {
        return null;
    }
};

export const htmlToMarkdown = async (html: string): Promise<string> => {
    try {
        const mod = await import('turndown');
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const TurndownService: any = (mod as any).default || (mod as any).TurndownService || (mod as any);
        const td = new TurndownService({
            headingStyle: 'atx',
            codeBlockStyle: 'fenced',
        });

        td.addRule('preserveTables', {
            filter: 'table',
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            replacement: function(content: string, node: any) {
                return '\n' + node.outerHTML + '\n';
            }
        });

        return td.turndown(html);
    } catch {
        return html.replace(/<[^>]*>/g, '');
    }
};
