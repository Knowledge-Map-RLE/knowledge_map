import React, { useEffect, useRef } from 'react';
import styles from '../../Article_editor.module.css';

interface YamlHeadingProps {
    value: string;
    placeholder?: string;
    readOnly?: boolean;
    onChange: (value: string) => void;
}

/**
 * Редактируемый заголовок статьи (contentEditable).
 * DOM неуправляемый: значение синхронизируется в обе стороны,
 * но во время фокуса внешние обновления не перезаписывают текст,
 * чтобы не сбивать позицию каретки.
 */
const YamlHeading: React.FC<YamlHeadingProps> = ({ value, placeholder, readOnly = false, onChange }) => {
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
            contentEditable={!readOnly}
            suppressContentEditableWarning
            spellCheck={false}
            data-placeholder={placeholder}
            onInput={readOnly ? undefined : (e) => onChange(e.currentTarget.textContent ?? '')}
            onBlur={readOnly ? undefined : (e) => onChange((e.currentTarget.textContent ?? '').trim())}
            onKeyDown={readOnly ? undefined : (e) => {
                if (e.key === 'Enter' || e.key === 'Escape') {
                    e.preventDefault();
                    e.currentTarget.blur();
                }
            }}
        />
    );
};

export default React.memo(YamlHeading);
