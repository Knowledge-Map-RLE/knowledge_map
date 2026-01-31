import { Link } from "react-router-dom";
import s from "./Site_map.module.css"

export default function Site_map() {
  return <div className={s.container}>
    <Link to="/">Карта знаний</Link>
    <Link to='/rle_databases'>Базы данных по РПЖ</Link>
    <Link to='/introduction'>Введение</Link>
    <Link to="/science_articles" title='Подпроект'>Карта научных статей</Link>
    <Link to="/data_extraction" title="Исходник → Markdown и данные">Извлечение данных</Link>
    <Link to="/nlp">Лингвистика</Link>
  </div>
}