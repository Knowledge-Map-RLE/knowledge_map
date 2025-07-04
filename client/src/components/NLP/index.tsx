import { useState, useEffect } from 'react'
import { getNLPMarkdown } from '../../services/api'
import s from './NLP.module.css'

export default function NLP() {
    const [markdownContent, setMarkdownContent] = useState<string>('Загрузка документа...')
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        const loadMarkdown = async () => {
            try {
                setIsLoading(true)
                setError(null)
                
                // Загружаем файл "Article example.md" из S3
                const response = await getNLPMarkdown('Article example.md')
                
                if (response.error || !response.content) {
                    throw new Error(response.error || 'Не удалось загрузить содержимое файла')
                }
                
                setMarkdownContent(response.content)
            } catch (err) {
                const errorMessage = err instanceof Error ? err.message : 'Неизвестная ошибка'
                console.error('Ошибка загрузки markdown:', errorMessage)
                setError(errorMessage)
                setMarkdownContent('Ошибка загрузки документа. Проверьте, что файл "Article example.md" загружен в bucket "markdown".')
            } finally {
                setIsLoading(false)
            }
        }

        loadMarkdown()
    }, [])

    return (
        <main className={s.nlp}>
            <div className={s.nlp_graph}>
                Граф лингвистических паттернов текста
            </div>
            
            <div className={s.nlp_text}>
                {isLoading && (
                    <div style={{ color: '#666', fontStyle: 'italic' }}>
                        🔄 Загрузка markdown документа из S3...
                    </div>
                )}
                
                {error && (
                    <div style={{ color: '#e74c3c', marginBottom: '1rem' }}>
                        ❌ Ошибка: {error}
                    </div>
                )}
                
                {!isLoading && !error && (
                    <div style={{ 
                        whiteSpace: 'pre-wrap', 
                        fontFamily: 'PT Sans, sans-serif',
                        lineHeight: '1.6',
                        color: '#333'
                    }}>
                        {markdownContent}
                    </div>
                )}
                
                {!isLoading && error && (
                    <div style={{ color: '#7f8c8d', marginTop: '1rem' }}>
                        💡 Убедитесь, что:
                        <ul style={{ marginTop: '0.5rem', paddingLeft: '1.5rem' }}>
                            <li>MinIO запущен (docker-compose up -d s3)</li>
                            <li>Bucket "markdown" создан</li>
                            <li>Файл "Article example.md" загружен в bucket</li>
                            <li>API сервер запущен и доступен</li>
                        </ul>
                    </div>
                )}
            </div>
            
            <div className={s.nlp_knowledge_map}>
                Паттерны → карта знаний
            </div>
        </main>
    )
}