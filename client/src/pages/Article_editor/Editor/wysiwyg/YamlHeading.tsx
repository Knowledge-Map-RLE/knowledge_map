import React, { useEffect, useRef } from 'react';
import styles from '../../Article_editor.module.css';

interface YamlHeadingProps {
    value: string;
    placeholder?: string;
    onChange: (value: string) => void;
}

/**
 * Редактируемый заголовок статьи (contentEditable).
 * DOM неуправляемый: значение синхронизируется в обе стороны,
 * но во время фокуса внешние обновления не перезаписывают текст,
 * чтобы не сбивать позицию каретки.
 */
const YamlHeading: React.FC<YamlHeadingProps> = ({ value, placeholder, onChange }) => {
    const ref = useRef<HTMLHeadingElement>(null);

    useEffect(() => {
        const el = ref.current;
        if (!el || document.activeElement === el || el.textContent === value) return;
        el.textContent = value;
    }, [value]);

    return (
        <h1
            ref={ref}
            className={styles.wyYamlHeading}
            contentEditable
            suppressContentEditableWarning
            spellCheck={false}
            data-placeholder={placeholder}
            onInput={(e) => onChange(e.currentTarget.textContent ?? '')}
            onBlur={(e) => onChange((e.currentTarget.textContent ?? '').trim())}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === 'Escape') {
                    e.preventDefault();
                    e.currentTarget.blur();
                }
            }}
        />
    );
};

export default React.memo(YamlHeading);
