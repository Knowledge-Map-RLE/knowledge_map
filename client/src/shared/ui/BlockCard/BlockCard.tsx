import s from './BlockCard.module.css';

export interface BlockCardReference {
    uid: string;
    type: 'block' | 'article' | 'statement';
    label: string;
    block_type?: number;
    order?: number;
}

interface Props {
    reference: BlockCardReference;
    onOpen?: (uid: string) => void;
    onRemove?: () => void;
}

const TYPE_META: Record<BlockCardReference['type'], { icon: string; label: string }> = {
    block: { icon: '📦', label: 'Блок' },
    article: { icon: '📄', label: 'Статья' },
    statement: { icon: '🔗', label: 'Триплет' },
};

export function BlockCard({ reference, onOpen, onRemove }: Props) {
    const meta = TYPE_META[reference.type] ?? TYPE_META.block;
    const shortUid = reference.uid.length > 10 ? `${reference.uid.slice(0, 8)}…` : reference.uid;
    const content = (
        <>
            <span className={s.icon}>{meta.icon}</span>
            <span className={s.body}>
                <span className={s.label}>{reference.label || meta.label}</span>
                <span className={s.meta}>
                    {meta.label}
                    {reference.block_type != null ? ` · тип ${reference.block_type}` : ''}
                    {reference.order != null ? ` · #${reference.order}` : ''}
                    <span className={s.uid}> · {shortUid}</span>
                </span>
            </span>
        </>
    );
    return (
        <div className={s.card}>
            {onOpen ? (
                <button className={s.main} onClick={() => onOpen(reference.uid)} title="Открыть">
                    {content}
                </button>
            ) : (
                <div className={s.main}>{content}</div>
            )}
            {onRemove && (
                <button className={s.remove} onClick={onRemove} title="Убрать">
                    ✕
                </button>
            )}
        </div>
    );
}
