import type { ArticleBlock, BlockType } from '../model';

export function blocksToText(blocks: ArticleBlock[]): string {
  return blocks.map((block) => {
    switch (block.type) {
      case 'code':
        return '```python\n' + block.content + '\n```';
      case 'formula':
        return '$$\n' + block.content + '\n$$';
      case 'image':
        return block.content;
      case 'table':
        return block.content;
      case 'separator':
        return block.content;
      case 'sentence':
        return block.content;
      case 'paragraph':
        return '';
    }
  }).join('\n\n');
}

export function generateBlockId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function highlightPython(code: string): string {
  let html = code
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  html = html.replace(
    /('{3}[\s\S]*?'{3}|"{3}[\s\S]*?"{3}|'[^']*'|"[^"]*"|`[^`]*`)/g,
    '<span class="codeString">$1</span>',
  );

  html = html.replace(/(#[^\n]*)/g, '<span class="codeComment">$1</span>');

  const kw =
    '\\b(async|await|def|class|return|if|elif|else|for|while|import|from|as|try|except|finally|with|yield|lambda|pass|break|continue|and|or|not|in|is|True|False|None|self|raise|global|nonlocal|del|print|range|len|type|int|str|float|list|dict|set|tuple|bool|assert|match|case)\\b';
  html = html.replace(new RegExp(kw, 'g'), '<span class="codeKeyword">$1</span>');

  html = html.replace(/(@\w+)/g, '<span class="codeDecorator">$1</span>');

  html = html.replace(
    /\b([a-zA-Z_]\w*)\s*\(/g,
    '<span class="codeFunction">$1</span>(',
  );

  html = html.replace(
    /\b(\d+\.?\d*)\b/g,
    '<span class="codeNumber">$1</span>',
  );

  return html;
}
