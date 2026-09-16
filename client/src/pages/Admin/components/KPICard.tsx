import { useState } from 'react';
import { FaArrowUp, FaArrowDown } from 'react-icons/fa';
import styles from '../Admin.module.css';

interface KPICardProps {
  title: string;
  value: number;
  prefix?: string;
  suffix?: string;
  tooltip?: string;
  trend?: 'up' | 'down' | null;
  color?: string;
}

const fmt = new Intl.NumberFormat('ru-RU', {
  maximumFractionDigits: 0,
});

const fmtDecimal = new Intl.NumberFormat('ru-RU', {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});

export default function KPICard({ title, value, prefix, suffix, tooltip, trend, color }: KPICardProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  const formatted = Math.abs(value) >= 1000 ? fmt.format(value) : fmtDecimal.format(value);

  return (
    <div
      className={styles.kpiCard}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      style={color ? { borderLeftColor: color, borderLeftWidth: 3 } : undefined}
    >
      <div className={styles.kpiTitle}>{title}</div>
      <div className={styles.kpiValue} style={color ? { color } : undefined}>
        {prefix ?? ''}{formatted}{suffix ?? ''}
      </div>
      {trend && (
        <span className={trend === 'up' ? styles.kpiTrendUp : styles.kpiTrendDown}>
          {trend === 'up' ? <FaArrowUp size={10} /> : <FaArrowDown size={10} />}
        </span>
      )}
      {tooltip && showTooltip && (
        <div className={styles.kpiTooltip}>{tooltip}</div>
      )}
    </div>
  );
}
