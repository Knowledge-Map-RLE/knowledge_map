import s from './Project_title.module.css'

function randomChoice<T>(arr: T[]): T {
  const index = Math.floor(Math.random() * arr.length);
  return arr[index];
}

const slogans = [
  'В БЕКОНЕЧНОСТЬ И ЕЩЁ ДАЛЬШЕ!',
  'ЗНАНИЯ — ЖИЗНЬ!',
  '∞ не lim',
]

export default function Project_title({ className='' }: { className: string }) {
    return <div className={`${s.main_menu} ${className}`}>
        <h1>КАРТА ЗНАНИЙ</h1>
        <div className={s.slogan}>{randomChoice(slogans)}</div>
    </div>
}