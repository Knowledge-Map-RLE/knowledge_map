import React, { useState, useEffect } from 'react';
import {
  checkDataAvailability,
  saveDocumentForTests,
  DataAvailabilityStatus,
  SaveForTestsRequest,
  SaveForTestsResponse,
} from '../../services/api';
import './SaveForTestsDialog.css';

interface SaveForTestsDialogProps {
  docId: string;
  documentTitle: string | null;
  onClose: () => void;
}

const SaveForTestsDialog: React.FC<SaveForTestsDialogProps> = ({
  docId,
  documentTitle,
  onClose,
}) => {
  const [availability, setAvailability] = useState<DataAvailabilityStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SaveForTestsResponse | null>(null);

  // Настройки экспорта
  const [validate, setValidate] = useState(true);

  useEffect(() => {
    // Проверяем доступность данных
    const fetchAvailability = async () => {
      try {
        setLoading(true);
        const data = await checkDataAvailability(docId);
        setAvailability(data);
      } catch (err: any) {
        setError(`Ошибка проверки данных: ${err.message}`);
      } finally {
        setLoading(false);
      }
    };

    fetchAvailability();
  }, [docId]);

  const handleSave = async () => {
    if (!availability?.is_ready) {
      setError('Документ не готов к экспорту. Проверьте наличие всех необходимых данных.');
      return;
    }

    try {
      setSaving(true);
      setError(null);

      const request: SaveForTestsRequest = {
        validate,
      };

      const response = await saveDocumentForTests(docId, request);
      setResult(response);
    } catch (err: any) {
      setError(`Ошибка экспорта: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const renderAvailabilityStatus = () => {
    if (loading) {
      return <div className="status-loading">Проверка доступности данных...</div>;
    }

    if (!availability) {
      return null;
    }

    return (
      <div className="availability-status">
        <h3>Статус данных документа:</h3>
        <div className="status-grid">
          <div className={`status-item ${availability.pdf_exists ? 'ready' : 'missing'}`}>
            <span className="status-icon">{availability.pdf_exists ? '✓' : '✗'}</span>
            <span>PDF файл</span>
          </div>
          <div className={`status-item ${availability.markdown_exists ? 'ready' : 'missing'}`}>
            <span className="status-icon">{availability.markdown_exists ? '✓' : '✗'}</span>
            <span>Markdown файл</span>
          </div>
          <div className={`status-item ${availability.has_annotations ? 'ready' : 'missing'}`}>
            <span className="status-icon">{availability.has_annotations ? '✓' : '✗'}</span>
            <span>Аннотации ({availability.annotation_count})</span>
          </div>
          <div className={`status-item ${availability.has_relations ? 'ready' : 'optional'}`}>
            <span className="status-icon">{availability.has_relations ? '✓' : '○'}</span>
            <span>Связи ({availability.relation_count})</span>
          </div>
          <div className={`status-item ${availability.has_chains ? 'ready' : 'missing'}`}>
            <span className="status-icon">{availability.has_chains ? '✓' : '✗'}</span>
            <span>Цепочки (обязательно)</span>
          </div>
          <div className={`status-item ${availability.has_patterns ? 'ready' : 'missing'}`}>
            <span className="status-icon">{availability.has_patterns ? '✓' : '✗'}</span>
            <span>Паттерны (обязательно)</span>
          </div>
        </div>

        {!availability.is_ready && (
          <div className="warning-box">
            <strong>⚠ Документ не готов к экспорту</strong>
            <p>
              Отсутствуют: {availability.missing_items.join(', ')}.
              <br />
              Данные попадут в тестовый датасет только после прохождения всех этапов обработки.
            </p>
          </div>
        )}
      </div>
    );
  };

  const renderExportSettings = () => {
    if (!availability?.is_ready) {
      return null;
    }

    return (
      <div className="export-settings">
        <h3>Настройки экспорта:</h3>

        <div className="mandatory-info">
          <p>
            <strong>Обязательные компоненты:</strong> PDF файл, Markdown, аннотации, паттерны, цепочки действий
          </p>
          <p>
            <strong>Имя датасета:</strong> генерируется автоматически с timestamp и случайным хэшем
          </p>
        </div>

        <div className="checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={validate}
              onChange={(e) => setValidate(e.target.checked)}
              disabled={saving}
            />
            <span>Валидировать датасет после экспорта</span>
          </label>
        </div>
      </div>
    );
  };

  const renderResult = () => {
    if (!result) {
      return null;
    }

    return (
      <div className="export-result">
        <div className="success-box">
          <h3>✓ Экспорт успешно завершен!</h3>
          <p>{result.message}</p>

          <div className="result-details">
            <p>
              <strong>Образец:</strong> {result.sample_id}
            </p>
            <p>
              <strong>Экспортировано файлов:</strong> {result.exported_files.length}
            </p>

            {result.exported_files.length > 0 && (
              <details>
                <summary>Список файлов</summary>
                <ul className="file-list">
                  {result.exported_files.map((file, idx) => (
                    <li key={idx}>{file}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>

          <div className="dvc-command">
            <h4>Команда для DVC:</h4>
            <code>{result.dvc_command}</code>
            <button
              className="copy-button"
              onClick={() => navigator.clipboard.writeText(result.dvc_command)}
            >
              Копировать
            </button>
          </div>

          {result.validation_result && (
            <details className="validation-details">
              <summary>Результат валидации</summary>
              <pre>{JSON.stringify(result.validation_result, null, 2)}</pre>
            </details>
          )}
        </div>

        <button className="close-button" onClick={onClose}>
          Закрыть
        </button>
      </div>
    );
  };

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-content" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <h2>Сохранить для тестов</h2>
          <button className="close-icon" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="dialog-body">
          {error && <div className="error-box">{error}</div>}

          {!result && (
            <>
              {renderAvailabilityStatus()}
              {renderExportSettings()}
            </>
          )}

          {result && renderResult()}
        </div>

        {!result && availability?.is_ready && (
          <div className="dialog-footer">
            <button className="cancel-button" onClick={onClose} disabled={saving}>
              Отмена
            </button>
            <button className="save-button" onClick={handleSave} disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default SaveForTestsDialog;
