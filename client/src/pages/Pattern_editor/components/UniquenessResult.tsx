import React from 'react';
import type { UniquenessResponse, AddStatementResponse } from '../../../services/api/uniqueness';

interface UniquenessResultProps {
    result: UniquenessResponse | null;
    addResult: AddStatementResponse | null;
    loading: boolean;
    error: string | null;
}

const STATUS_COLORS: Record<string, string> = {
    SAME: '#4CAF50',
    UNCERTAIN: '#FF9800',
    DIFFERENT: '#2196F3',
    NEW: '#9C27B0',
    UNKNOWN: '#9e9e9e',
};

/**
 * Панель результата проверки уникальности.
 * Показывает статус, ссылку на существующее знание и кандидатов.
 */
export const UniquenessResult: React.FC<UniquenessResultProps> = ({
    result,
    addResult,
    loading,
    error,
}) => {
    if (loading) {
        return (
            <div style={panelStyle}>
                <h4 style={{ margin: '0 0 8px' }}>Проверка уникальности…</h4>
                <div style={{ fontSize: '12px', color: '#999' }}>
                    Выполняется fingerprint → vector search → cosine. Пожалуйста, подождите.
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div style={{ ...panelStyle, borderColor: '#F44336' }}>
                <h4 style={{ margin: '0 0 8px', color: '#F44336' }}>Ошибка</h4>
                <div style={{ fontSize: '12px' }}>{error}</div>
            </div>
        );
    }

    if (addResult) {
        return (
            <div style={{ ...panelStyle, borderColor: addResult.success ? '#4CAF50' : '#FF9800' }}>
                <h4 style={{ margin: '0 0 8px' }}>Результат добавления</h4>
                <div>
                    <StatusBadge status={addResult.uniqueness_status} />
                    <div style={{ fontSize: '12px', marginTop: '8px' }}>{addResult.message}</div>
                    {addResult.statement_id && (
                        <div style={{ fontSize: '11px', marginTop: '4px' }}>
                            ID: <code>{addResult.statement_id}</code>
                        </div>
                    )}
                </div>
            </div>
        );
    }

    if (!result) {
        return <div style={panelStyle}>Постройте паттерн и нажмите «Проверить». Результат появится здесь.</div>;
    }

    const color = STATUS_COLORS[result.status] ?? '#9e9e9e';

    return (
        <div style={{ ...panelStyle, borderColor: color }}>
            <h4 style={{ margin: '0 0 8px' }}>Результат проверки</h4>
            <div>
                <StatusBadge status={result.status} />
                {result.status === 'SAME' && result.existing_statement_id && (
                    <div style={{ fontSize: '12px', marginTop: '8px', color: '#4CAF50' }}>
                        «Такое знание уже есть»
                        <div>
                            Ссылка: <code>{result.existing_statement_id}</code>
                        </div>
                        <div style={{ color: '#999' }}>Уверенность: {(result.confidence * 100).toFixed(1)}%</div>
                    </div>
                )}
                {result.status === 'UNCERTAIN' && (
                    <div style={{ fontSize: '12px', marginTop: '8px', color: '#FF9800' }}>
                        Возможно дубликат — требуется проверка.
                        <div style={{ color: '#999' }}>
                            Лучшее сходство: {(result.confidence * 100).toFixed(1)}%
                        </div>
                    </div>
                )}
                {result.status === 'NEW' && (
                    <div style={{ fontSize: '12px', marginTop: '8px', color: '#9C27B0' }}>
                        Это новое знание. Можно добавить.
                    </div>
                )}
                {result.status === 'DIFFERENT' && (
                    <div style={{ fontSize: '12px', marginTop: '8px', color: '#2196F3' }}>
                        Знание не найдено в графе.
                    </div>
                )}

                {result.candidates && result.candidates.length > 0 && (
                    <div style={{ marginTop: '10px' }}>
                        <div style={{ fontSize: '11px', fontWeight: 600, color: '#666' }}>Кандидаты:</div>
                        {result.candidates.slice(0, 5).map((c) => (
                            <div
                                key={c.statement_id}
                                style={{
                                    fontSize: '11px',
                                    padding: '4px 6px',
                                    margin: '4px 0',
                                    background: '#f5f5f5',
                                    borderRadius: '4px',
                                }}
                            >
                                <span style={{ color: '#444' }}>
                                    {c.subject_text} {c.predicate} {c.object_text}
                                </span>{' '}
                                <span style={{ color: '#999' }}>({(c.similarity * 100).toFixed(1)}%)</span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
    const colors: Record<string, { bg: string; text: string }> = {
        SAME: { bg: '#4CAF50', text: '#fff' },
        UNCERTAIN: { bg: '#FF9800', text: '#fff' },
        DIFFERENT: { bg: '#2196F3', text: '#fff' },
        NEW: { bg: '#9C27B0', text: '#fff' },
        UNKNOWN: { bg: '#9e9e9e', text: '#fff' },
    };
    const c = colors[status] ?? colors.UNKNOWN;
    const labels: Record<string, string> = {
        SAME: 'Уже есть',
        UNCERTAIN: 'Возможный дубль',
        DIFFERENT: 'Новое',
        NEW: 'Новое',
        UNKNOWN: 'Неизвестно',
    };
    return (
        <span
            style={{
                background: c.bg,
                color: c.text,
                padding: '3px 8px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: 600,
            }}
        >
            {labels[status] ?? status}
        </span>
    );
};

const panelStyle: React.CSSProperties = {
    padding: '12px',
    border: '2px solid #e0e0e0',
    borderRadius: '8px',
    background: '#fff',
    fontSize: '13px',
};
