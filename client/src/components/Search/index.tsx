import s from './Search.module.css'

export default function Search({ className='' }: { className: string }) {
    return <div className={`${s.search_panel} ${className}`}>
        <div className={s.logo}></div>
        <input type='text' className={s.search} placeholder='Введён запрос + Enter = Поиск' />
    </div>
}