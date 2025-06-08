import s from './User.module.css'

export default function User() {
    return <div className={s.user}>
        <div className={s.avatar}></div>
        <div className={s.user_info}>
          <div className={s.name}>Димка Прокофьев</div>
          <div className={s.info}>@dima_prokofev</div>
        </div>
    </div>
}