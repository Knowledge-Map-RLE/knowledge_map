import s from './User.module.css'

export default function User({ className='' }: { className: string }) {
    return <div className={`${s.user} ${className}`}>
        <div className={s.avatar}></div>
        <div className={s.user_info}>
          <div className={s.name}>Димка Прокофьев</div>
          <div className={s.info}>УР: 32 | @dima_prokofev</div>
        </div>
    </div>
}