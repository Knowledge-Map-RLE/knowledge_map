/**
 * Hook для валидации markdown через API
 */
import { useState, useCallback } from 'react';
import type { ValidationResponse } from '../components/ValidationErrorAlert';

interface UseMarkdownValidationOptions {
  apiUrl?: string;
  strictMode?: boolean;
}

interface UseMarkdownValidationReturn {
  validation: ValidationResponse | null;
  isValidating: boolean;
  error: string | null;
  validateMarkdown: (markdown: string, strictMode?: boolean) => Promise<ValidationResponse | null>;
  clearValidation: () => void;
}

/**
 * Hook для валидации markdown документа
 * @param options - Опции конфигурации
 * @returns Объект с функциями и состоянием валидации
 */
export const useMarkdownValidation = (
  options: UseMarkdownValidationOptions = {}
): UseMarkdownValidationReturn => {
  const {
    apiUrl = '/api/data_extraction/markdown/validate',
    strictMode = false,
  } = options;

  const [validation, setValidation] = useState<ValidationResponse | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validateMarkdown = useCallback(
    async (markdown: string, customStrictMode?: boolean): Promise<ValidationResponse | null> => {
      if (!markdown || markdown.trim() === '') {
        setError('Markdown текст не может быть пустым');
        setValidation(null);
        return null;
      }

      setIsValidating(true);
      setError(null);

      try {
        const response = await fetch(apiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            markdown,
            strict_mode: customStrictMode ?? strictMode,
          }),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data: ValidationResponse = await response.json();
        setValidation(data);
        return data;
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : 'Неизвестная ошибка при валидации';
        setError(errorMessage);
        setValidation(null);
        console.error('Validation error:', err);
        return null;
      } finally {
        setIsValidating(false);
      }
    },
    [apiUrl, strictMode]
  );

  const clearValidation = useCallback(() => {
    setValidation(null);
    setError(null);
  }, []);

  return {
    validation,
    isValidating,
    error,
    validateMarkdown,
    clearValidation,
  };
};

export default useMarkdownValidation;
