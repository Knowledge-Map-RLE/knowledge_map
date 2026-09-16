import type { Period } from '../model';
import styles from '../Admin.module.css';

interface PeriodSelectorProps {
  value: Period;
  onChange: (period: Period) => void;
}

const PERIODS: { value: Period; label: string }[] = [
  { value: 'day', label: 'День' },
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'quarter', label: 'Квартал' },
  { value: 'year', label: 'Год' },
];

export default function PeriodSelector({ value, onChange }: PeriodSelectorProps) {
  return (
    <div className={styles.periodSelector}>
      {PERIODS.map((p) => (
        <button
          key={p.value}
          type="button"
          className={`${styles.periodBtn} ${value === p.value ? styles.periodBtnActive : ''}`}
          onClick={() => onChange(p.value)}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
