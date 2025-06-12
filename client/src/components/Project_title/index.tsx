import s from './Project_title.module.css'

export default function Project_title({ className='' }: { className: string }) {
    return <div className={`${s.main_menu} ${className}`}>
        <h1>КАРТА ЗНАНИЙ</h1>
        <div className={s.slogan}>В БЕКОНЕЧНОСТЬ И ЕЩЁ ДАЛЬШЕ!</div>
    </div>
}