import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faBars } from '@fortawesome/free-solid-svg-icons'
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

const links = [
  { to: '/', label: 'Главная — Лендинг' },
  { to: '/km', label: 'Карта знаний' },
  { to: '/introduction', label: 'Введение' },
  { to: '/science_articles', label: 'Карта научных статей' },
  { to: '/data_extraction', label: 'Извлечение данных' },
  { to: '/pattern_analysis', label: 'Анализ паттернов' },
]

export default function Project_title({ className = '' }: { className: string }) {
  const [open, setOpen] = useState(false)

  return (
    <div className={s.main_menu} onClick={() => setOpen(o => !o)}>
      <h1>КАРТА ЗНАНИЙ</h1>
      <div className={s.slogan}>{randomChoice()}</div>
      <FontAwesomeIcon icon={faBars} className={`${s.arrow} ${open ? s.arrow_open : ''}`} />
      {open && (
        <nav className={s.dropdown}>
          {links.map(({ to, label }) => (
            <Link key={to} to={to} className={s.link} onClick={() => setOpen(false)}>
              {label}
            </Link>
          ))}
        </nav>
      )}
    </div>
  )
}