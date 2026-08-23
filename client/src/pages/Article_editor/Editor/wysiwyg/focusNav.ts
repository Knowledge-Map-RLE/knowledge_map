const LINE_ATTR = 'data-wy-line';
const FIELD_ATTR = 'data-wy-field';

function esc(value: string): string {
    if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') {
        return CSS.escape(value);
    }
    return value.replace(/["\\\]]/g, '\\$&');
}

export function queryFieldEl(root: HTMLElement | null | undefined, lineId: string, fieldKey: string): HTMLElement | null {
    if (!root) return null;
    return root.querySelector<HTMLElement>(`[${LINE_ATTR}="${esc(lineId)}"][${FIELD_ATTR}="${esc(fieldKey)}"]`);
}

export function queryLineEls(root: HTMLElement | null | undefined): HTMLElement[] {
    if (!root) return [];
    return Array.from(root.querySelectorAll<HTMLElement>(`[${LINE_ATTR}]`));
}

export function queryLineFieldEls(root: HTMLElement | null | undefined, lineId: string): HTMLElement[] {
    if (!root) return [];
    return Array.from(root.querySelectorAll<HTMLElement>(`[${LINE_ATTR}="${esc(lineId)}"][${FIELD_ATTR}]`));
}

export function focusFieldEl(el: HTMLElement | null | undefined): boolean {
    if (!el) return false;
    el.focus();
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
        const len = el.value.length;
        try {
            el.setSelectionRange(len, len);
        } catch {
            // some input types do not support setSelectionRange
        }
    }
    return document.activeElement === el;
}

export interface FocusedFieldInfo {
    lineId: string;
    fieldKey: string;
    el: HTMLElement;
}

export function getFocusedFieldInfo(): FocusedFieldInfo | null {
    const active = document.activeElement as HTMLElement | null;
    if (!active) return null;
    const holder = active.closest<HTMLElement>(`[${FIELD_ATTR}]`);
    if (!holder) return null;
    return {
        el: holder,
        fieldKey: holder.getAttribute(FIELD_ATTR) ?? '',
        lineId: holder.getAttribute(LINE_ATTR) ?? '',
    };
}

export { LINE_ATTR, FIELD_ATTR };
