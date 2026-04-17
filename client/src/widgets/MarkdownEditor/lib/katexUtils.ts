import renderMathInElement from 'katex/contrib/auto-render';

export const renderMathInTables = (container: HTMLElement): void => {
    const tables = container.querySelectorAll('table');
    tables.forEach((table) => {
        renderMathInElement(table, {
            delimiters: [
                { left: '$$', right: '$$', display: true },
                { left: '$', right: '$', display: false },
            ],
            throwOnError: false,
        });
    });
};

export const wrapKatexElements = (container: HTMLElement): void => {
    const katexEls = container.querySelectorAll<HTMLElement>('.katex');
    katexEls.forEach((el) => {
        if (el.closest('.km-katex-wrap') || el.parentElement?.classList.contains('km-katex-wrap')) return;

        const latex = el.getAttribute('data-latex') || el.querySelector('annotation[encoding="application/x-tex"]')?.textContent || '';
        if (!latex) return;

        const isDisplay = el.classList.contains('katex-display') || el.closest('.katex-display') !== null;

        const wrap = document.createElement('span');
        wrap.className = `km-katex-wrap${isDisplay ? ' block' : ''}`;

        const btn = document.createElement('button');
        btn.className = 'km-katex-copy';
        btn.textContent = 'Copy LaTeX';
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            navigator.clipboard.writeText(latex).then(() => {
                btn.textContent = 'Скопировано!';
                btn.classList.add('copied');
                setTimeout(() => {
                    btn.textContent = 'Copy LaTeX';
                    btn.classList.remove('copied');
                }, 1500);
            });
        });

        el.parentNode?.insertBefore(wrap, el);
        wrap.appendChild(el);
        wrap.appendChild(btn);
    });
};
