import { useState, useCallback } from 'react';
import { decomposeGoal } from '../../services/api';
import type { GoalPlanTree } from '../../services/api';

interface GoalDecompositionPanelProps {
  /** Вызывается после успешной декомпозиции — чтобы перезагрузить карту. */
  onDecomposed?: (tree: GoalPlanTree, planId: string) => void;
}

/**
 * Правая панель страницы /km: поле ввода цели, жёлтая кнопка
 * «Декомпозировать цель (обратное планирование)» и дерево полученного плана.
 */
const GoalDecompositionPanel: React.FC<GoalDecompositionPanelProps> = ({ onDecomposed }) => {
  const [goal, setGoal] = useState('');
  const [tree, setTree] = useState<GoalPlanTree | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDecompose = useCallback(async () => {
    const text = goal.trim();
    if (!text) {
      setError('Введите текст цели');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await decomposeGoal(text);
      if (!data?.success) {
        setError(data?.message || 'Не удалось декомпозировать цель');
        return;
      }
      setTree(data.tree);
      onDecomposed?.(data.tree, data.plan_id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ошибка запроса декомпозиции');
    } finally {
      setLoading(false);
    }
  }, [goal, onDecomposed]);

  return (
    <div style={{ flex: '1 1 0', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 12, color: '#555', fontWeight: 600 }}>
        Декомпозиция цели
      </div>
      <textarea
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
        placeholder="Введите цель на естественном языке..."
        rows={3}
        style={{
          width: '100%',
          boxSizing: 'border-box',
          padding: '6px 8px',
          backgroundColor: '#ffffff',
          color: '#333',
          border: '1px solid #ccc',
          borderRadius: '4px',
          fontSize: '13px',
          resize: 'vertical',
          fontFamily: 'inherit',
        }}
      />
      <button
        onClick={handleDecompose}
        disabled={loading}
        style={{
          padding: '8px 10px',
          backgroundColor: loading ? '#f5c93d' : '#f9d423',
          color: '#3b2f00',
          border: 'none',
          borderRadius: '6px',
          fontWeight: 700,
          fontSize: '13px',
          cursor: loading ? 'default' : 'pointer',
          opacity: loading ? 0.7 : 1,
          boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
        }}
      >
        {loading ? 'Декомпозируем...' : 'Декомпозировать цель (обратное планирование)'}
      </button>

      {error && (
        <div style={{ fontSize: 12, color: '#b91c1c', padding: '2px 8px' }}>
          {error}
        </div>
      )}

      {tree && (
        <div style={{ fontSize: 12, color: '#555' }}>
          План «{tree.goal}» создан
        </div>
      )}

      {tree && (
        <div
          style={{
            flex: '1 1 0',
            minHeight: 0,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            paddingRight: 2,
          }}
        >
          {tree.items.map((item) => (
            <div
              key={item.id}
              style={{
                padding: '5px 8px',
                backgroundColor: item.level === 0 ? '#fff7ed' : '#fff',
                border: item.level === 0 ? '1px solid #fcd34d' : '1px solid #eee',
                borderRadius: '4px',
                fontSize: '12px',
                lineHeight: 1.3,
                marginLeft: item.level * 12,
              }}
            >
              <span
                style={{
                  display: 'block',
                  color: '#9ca3af',
                  fontSize: 10,
                  fontFamily: 'monospace',
                }}
              >
                {item.id} ·{item.kind}
              </span>
              <span style={{ color: '#333' }}>{item.text}</span>
              {item.rationale && (
                <span
                  style={{
                    display: 'block',
                    color: '#888',
                    fontSize: 11,
                    marginTop: 2,
                  }}
                >
                  ← {item.rationale}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default GoalDecompositionPanel;