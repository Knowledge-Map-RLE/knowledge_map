import s from './Knowledge_map_ui.module.css'
import Main_menu from '../Main_menu'
import Search from '../Search'
import User from '../User'

export default function Knowledge_map_ui() {
    return <div className={s.interface}>
        <Main_menu />
        <Search />
        <User />
        <div className={s.left}>4</div>
        <div className={s.center}>5</div>
        <div className={s.right}>6</div>
        <div className={s.info}>7</div>
        <div className={s.bot}>8</div>
        <div className={s.minimap}>9</div>
    </div>
}