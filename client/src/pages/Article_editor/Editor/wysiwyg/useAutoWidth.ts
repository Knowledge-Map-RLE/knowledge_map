import { useEffect, useRef } from 'react';

let mirror: HTMLSpanElement | null = null;

function getMirror(): HTMLSpanElement {
    if (!mirror) {
        mirror = document.createElement('span');
        const s = mirror.style;
        s.position = 'absolute';
        s.top = '-9999px';
        s.left = '0';
        s.visibility = 'hidden';
        s.whiteSpace = 'pre';
        document.body.appendChild(mirror);
    }
    return mirror;
}

/**
 * Автоширина однострочного input по содержимому.
 * В Chromium/Opera используется нативный `field-sizing: content` (задан в CSS),
 * в остальных браузерах ширина считается через скрытое зеркало с тем же шрифтом.
 */
export function useAutoWidth(value: string) {
    const ref = useRef<HTMLInputElement>(null);

    useEffect(() => {
        const el = ref.current;
        if (!el || 'fieldSizing' in el.style) return;
        const span = getMirror();
        span.style.font = getComputedStyle(el).font;
        span.textContent = value || el.placeholder || '';
        el.style.width = `${Math.max(span.offsetWidth + 6, 20)}px`;
    });

    return ref;
}
