import s from './Project_title.module.css'

function randomChoice(): string {
  const slogans = [
    'В БЕКОНЕЧНОСТЬ И ЕЩЁ ДАЛЬШЕ!',
    'ЗНАНИЯ — ЖИЗНЬ!',
    '∞ не lim',
  ]
  const index = Math.floor(Math.random() * slogans.length);

  return slogans[index];
}


export default function Project_title({ className='' }: { className: string }) {
    return <div className={`${s.main_menu} ${className}`}>
        <h1>КАРТА ЗНАНИЙ</h1>
        <div className={s.slogan}>{randomChoice()}</div>
    </div>
}