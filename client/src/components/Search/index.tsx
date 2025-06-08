import s from './Search.module.css'

export default function Search() {
    return <div className={s.search_panel}>
        <div className={s.logo}></div>
        <input type='text' className={s.search} placeholder='Ведён запрос + Enter = Поиск' />
    </div>
}