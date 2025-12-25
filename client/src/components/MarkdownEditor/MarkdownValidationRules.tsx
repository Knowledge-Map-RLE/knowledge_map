/**
 * Modal окно с правилами валидации канонического Markdown
 */
import React from 'react';
import styles from './MarkdownValidationRules.module.css';

interface MarkdownValidationRulesProps {
  isOpen: boolean;
  onClose: () => void;
}

export const MarkdownValidationRules: React.FC<MarkdownValidationRulesProps> = ({
  isOpen,
  onClose,
}) => {
  if (!isOpen) return null;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h2>📋 Правила канонического Markdown</h2>
          <button className={styles.closeButton} onClick={onClose}>
            ✕
          </button>
        </div>

        <div className={styles.content}>
          {/* 1. YAML Frontmatter */}
          <section className={styles.rule}>
            <h3>1. 📝 YAML Frontmatter (опционально)</h3>
            <p className={styles.description}>
              Документ может начинаться с блока метаданных в формате YAML
            </p>

            <div className={styles.correct}>
              <h4>✅ Правильно:</h4>
              <pre>{`---
title: Название статьи
author: Иван Иванов
date: 2024-01-01
tags:
  - тег1
  - тег2
---

# Основной контент`}</pre>
            </div>

            <div className={styles.incorrect}>
              <h4>❌ Неправильно:</h4>
              <pre>{`---
title: Название статьи
author: Иван Иванов

# Контент (frontmatter не закрыт)

---
invalid: yaml: [syntax
---`}</pre>
            </div>

            <p className={styles.rule_text}>
              <strong>Требования:</strong>
              <ul>
                <li>Если есть frontmatter, он должен начинаться с <code>---</code></li>
                <li>Завершаться с <code>---</code> на отдельной строке</li>
                <li>Содержимое должно быть валидным YAML</li>
              </ul>
            </p>
          </section>

          {/* 2. H1 заголовок */}
          <section className={styles.rule}>
            <h3>2. 📌 Один заголовок H1</h3>
            <p className={styles.description}>
              Документ должен содержать ровно один заголовок первого уровня
            </p>

            <div className={styles.correct}>
              <h4>✅ Правильно:</h4>
              <pre>{`# Основной заголовок

## Раздел 1
Содержимое

## Раздел 2
### Подраздел 2.1
### Подраздел 2.2`}</pre>
            </div>

            <div className={styles.incorrect}>
              <h4>❌ Неправильно:</h4>
              <pre>{`## Раздел 1
Нет H1 заголовка!

---

# Первый H1

## Раздел 2

# Второй H1 (дубликат!)`}</pre>
            </div>

            <p className={styles.rule_text}>
              <strong>Требования:</strong>
              <ul>
                <li>Ровно <strong>один</strong> заголовок <code># Название</code></li>
                <li>Можно использовать H2 (<code>##</code>), H3 (<code>###</code>) и глубже</li>
                <li>H1 должен быть основным названием статьи</li>
              </ul>
            </p>
          </section>

          {/* 3. Таблицы */}
          <section className={styles.rule}>
            <h3>3. 📊 Только HTML таблицы</h3>
            <p className={styles.description}>
              Таблицы должны быть в формате HTML, а не Markdown
            </p>

            <div className={styles.correct}>
              <h4>✅ Правильно:</h4>
              <pre>{`<table>
  <tr>
    <td>Ячейка 1</td>
    <td>Ячейка 2</td>
  </tr>
  <tr>
    <td>Данные 1</td>
    <td>Данные 2</td>
  </tr>
</table>`}</pre>
            </div>

            <div className={styles.incorrect}>
              <h4>❌ Неправильно:</h4>
              <pre>{`| Заголовок 1 | Заголовок 2 |
|-------------|-------------|
| Данные 1    | Данные 2    |`}</pre>
            </div>

            <p className={styles.rule_text}>
              <strong>Требования:</strong>
              <ul>
                <li>Использовать HTML теги: <code>&lt;table&gt;</code>, <code>&lt;tr&gt;</code>, <code>&lt;td&gt;</code></li>
                <li>❌ Запрещены markdown таблицы с <code>|---|---|</code></li>
              </ul>
            </p>
          </section>

          {/* 4. Изображения */}
          <section className={styles.rule}>
            <h3>4. 🖼️ Только HTML изображения</h3>
            <p className={styles.description}>
              Изображения должны быть в формате HTML
            </p>

            <div className={styles.correct}>
              <h4>✅ Правильно:</h4>
              <pre>{`<img src="image.png" alt="Описание изображения">

<figure>
  <img src="image.png" alt="Описание">
  <figcaption>Подпись под изображением</figcaption>
</figure>`}</pre>
            </div>

            <div className={styles.incorrect}>
              <h4>❌ Неправильно:</h4>
              <pre>{`![Описание изображения](image.png)`}</pre>
            </div>

            <p className={styles.rule_text}>
              <strong>Требования:</strong>
              <ul>
                <li>Использовать HTML <code>&lt;img&gt;</code> тег</li>
                <li>Можно использовать <code>&lt;figure&gt;</code> с <code>&lt;figcaption&gt;</code></li>
                <li>❌ Запрещены markdown изображения <code>![alt](url)</code></li>
              </ul>
            </p>
          </section>

          {/* 5. Ссылки и цитаты */}
          <section className={styles.rule}>
            <h3>5. 🔗 Двунаправленные ссылки и цитаты</h3>
            <p className={styles.description}>
              Каждая цитата должна соответствовать записи в разделе References
            </p>

            <div className={styles.correct}>
              <h4>✅ Правильно:</h4>
              <pre>{`# Статья о исследованиях

Первое исследование показало [1], что...
Второе исследование [2] подтверждает это.
Первое исследование [1] также упоминает...

## References

[1]: Smith, J. et al. (2023). First study. Journal of Research, 15(3), 45-67.
[2]: Johnson, M. (2023). Second study. Nature, 580(7825), 123-125.`}</pre>
            </div>

            <div className={styles.incorrect}>
              <h4>❌ Неправильно:</h4>
              <pre>{`# Статья

Цитата [1] без соответствующей записи.
Цитата [2].

## References

[1]: First reference.
[3]: Reference без цитирования в тексте.
[1]: Дубликат номера 1!`}</pre>
            </div>

            <p className={styles.rule_text}>
              <strong>Требования:</strong>
              <ul>
                <li>Каждая цитата <code>[N]</code> должна иметь запись <code>[N]: текст</code> в References</li>
                <li>Каждая запись References должна быть процитирована хотя бы раз</li>
                <li>Раздел <code>## References</code> должен быть в конце документа</li>
                <li>Формат ссылки: <code>[номер]: библиографический текст</code></li>
                <li>Номера ссылок должны быть уникальными</li>
              </ul>
            </p>
          </section>

          {/* Summary */}
          <section className={styles.summary}>
            <h3>📝 Краткая сводка</h3>
            <table className={styles.summaryTable}>
              <thead>
                <tr>
                  <th>Элемент</th>
                  <th>Требование</th>
                  <th>Примечание</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Frontmatter</td>
                  <td>Опционально</td>
                  <td>Если есть, должен быть в валидном YAML</td>
                </tr>
                <tr>
                  <td>H1</td>
                  <td>Ровно 1</td>
                  <td>Основной заголовок статьи</td>
                </tr>
                <tr>
                  <td>Таблицы</td>
                  <td>Только HTML</td>
                  <td>HTML теги &lt;table&gt;</td>
                </tr>
                <tr>
                  <td>Изображения</td>
                  <td>Только HTML</td>
                  <td>HTML теги &lt;img&gt;</td>
                </tr>
                <tr>
                  <td>Ссылки</td>
                  <td>Двунаправленные</td>
                  <td>Цитаты ↔ References</td>
                </tr>
              </tbody>
            </table>
          </section>
        </div>

        <div className={styles.footer}>
          <button className={styles.closeButtonFooter} onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};

export default MarkdownValidationRules;
