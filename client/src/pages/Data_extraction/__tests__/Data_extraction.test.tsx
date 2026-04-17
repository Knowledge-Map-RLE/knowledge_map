/**
 * Тесты для компонента Data_extraction.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import Data_extraction from '../index';

// Мокаем fetch
global.fetch = jest.fn();

// Мокаем window.URL.createObjectURL
Object.defineProperty(window, 'URL', {
  value: {
    createObjectURL: jest.fn(() => 'mocked-url'),
    revokeObjectURL: jest.fn(),
  },
});

describe('Data_extraction Component', () => {
  beforeEach(() => {
    (fetch as jest.Mock).mockClear();
  });

  test('рендерится корректно', () => {
    render(<Data_extraction />);
    
    expect(screen.getByText('Загрузка PDF документов')).toBeInTheDocument();
    expect(screen.getByText('Просмотр и аннотации')).toBeInTheDocument();
    expect(screen.getByText('Перетащите PDF файл сюда или нажмите для выбора')).toBeInTheDocument();
  });

  test('отображает область загрузки файлов', () => {
    render(<Data_extraction />);
    
    const uploadArea = screen.getByText('Перетащите PDF файл сюда или нажмите для выбора');
    expect(uploadArea).toBeInTheDocument();
    
    const fileInput = document.querySelector('input[type="file"]');
    expect(fileInput).toBeInTheDocument();
    expect(fileInput).toHaveAttribute('accept', '.pdf');
  });

  test('обрабатывает выбор файла', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        document_id: 'test-doc-id',
        md5_hash: 'test-hash',
        already_exists: false
      })
    });

    render(<Data_extraction />);
    
    const file = new File(['test pdf content'], 'test.pdf', { type: 'application/pdf' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    
    fireEvent.change(fileInput, { target: { files: [file] } });
    
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/pdf/upload', expect.objectContaining({
        method: 'POST',
        body: expect.any(FormData)
      }));
    });
  });

  test('показывает ошибку для не-PDF файлов', async () => {
    render(<Data_extraction />);
    
    const file = new File(['test content'], 'test.txt', { type: 'text/plain' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    
    fireEvent.change(fileInput, { target: { files: [file] } });
    
    await waitFor(() => {
      expect(screen.getByText('Пожалуйста, выберите PDF файл')).toBeInTheDocument();
    });
  });

  test('обрабатывает drag and drop', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        document_id: 'test-doc-id',
        md5_hash: 'test-hash',
        already_exists: false
      })
    });

    render(<Data_extraction />);
    
    const uploadArea = screen.getByText('Перетащите PDF файл сюда или нажмите для выбора').closest('div');
    const file = new File(['test pdf content'], 'test.pdf', { type: 'application/pdf' });
    
    fireEvent.dragOver(uploadArea!, {
      dataTransfer: {
        files: [file]
      }
    });
    
    fireEvent.drop(uploadArea!, {
      dataTransfer: {
        files: [file]
      }
    });
    
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/pdf/upload', expect.objectContaining({
        method: 'POST',
        body: expect.any(FormData)
      }));
    });
  });

  test('загружает список документов', async () => {
    const mockDocuments = [
      {
        uid: 'doc1',
        original_filename: 'test1.pdf',
        md5_hash: 'hash1',
        upload_date: '2023-12-01T00:00:00Z',
        processing_status: 'uploaded',
        is_processed: false
      },
      {
        uid: 'doc2',
        original_filename: 'test2.pdf',
        md5_hash: 'hash2',
        upload_date: '2023-12-02T00:00:00Z',
        processing_status: 'annotated',
        is_processed: true
      }
    ];

    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => mockDocuments
    });

    render(<Data_extraction />);
    
    await waitFor(() => {
      expect(screen.getByText('test1.pdf')).toBeInTheDocument();
      expect(screen.getByText('test2.pdf')).toBeInTheDocument();
    });
  });

  test('показывает статус документов', async () => {
    const mockDocuments = [
      {
        uid: 'doc1',
        original_filename: 'test1.pdf',
        md5_hash: 'hash1',
        upload_date: '2023-12-01T00:00:00Z',
        processing_status: 'uploaded',
        is_processed: false
      }
    ];

    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => mockDocuments
    });

    render(<Data_extraction />);
    
    await waitFor(() => {
      expect(screen.getByText('Загружен')).toBeInTheDocument();
    });
  });

  test('позволяет выбрать документ', async () => {
    const mockDocuments = [
      {
        uid: 'doc1',
        original_filename: 'test1.pdf',
        md5_hash: 'hash1',
        upload_date: '2023-12-01T00:00:00Z',
        processing_status: 'uploaded',
        is_processed: false
      }
    ];

    const mockAnnotations = [
      {
        uid: 'ann1',
        annotation_type: 'title',
        content: 'Test Title',
        confidence: 0.95,
        page_number: 1
      }
    ];

    (fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDocuments
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAnnotations
      });

    render(<Data_extraction />);
    
    await waitFor(() => {
      expect(screen.getByText('test1.pdf')).toBeInTheDocument();
    });

    const documentItem = screen.getByText('test1.pdf').closest('div');
    fireEvent.click(documentItem!);
    
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/pdf/document/doc1/annotations');
    });
  });

  test('запускает аннотацию документа', async () => {
    const mockDocuments = [
      {
        uid: 'doc1',
        original_filename: 'test1.pdf',
        md5_hash: 'hash1',
        upload_date: '2023-12-01T00:00:00Z',
        processing_status: 'uploaded',
        is_processed: false
      }
    ];

    (fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDocuments
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, message: 'Аннотация запущена' })
      });

    render(<Data_extraction />);
    
    await waitFor(() => {
      expect(screen.getByText('test1.pdf')).toBeInTheDocument();
    });

    const annotateButton = screen.getByText('Аннотировать');
    fireEvent.click(annotateButton);
    
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/pdf/document/doc1/annotate', expect.objectContaining({
        method: 'POST',
        body: expect.any(FormData)
      }));
    });
  });

  test('показывает PDF в iframe', async () => {
    const mockDocuments = [
      {
        uid: 'doc1',
        original_filename: 'test1.pdf',
        md5_hash: 'hash1',
        upload_date: '2023-12-01T00:00:00Z',
        processing_status: 'uploaded',
        is_processed: false
      }
    ];

    (fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDocuments
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => []
      });

    render(<Data_extraction />);
    
    await waitFor(() => {
      expect(screen.getByText('test1.pdf')).toBeInTheDocument();
    });

    const documentItem = screen.getByText('test1.pdf').closest('div');
    fireEvent.click(documentItem!);
    
    await waitFor(() => {
      const iframe = document.querySelector('iframe');
      expect(iframe).toBeInTheDocument();
      expect(iframe).toHaveAttribute('src', '/api/pdf/document/doc1/download');
    });
  });

  test('генерирует Markdown из аннотаций', async () => {
    const mockDocuments = [
      {
        uid: 'doc1',
        original_filename: 'test1.pdf',
        md5_hash: 'hash1',
        upload_date: '2023-12-01T00:00:00Z',
        processing_status: 'annotated',
        is_processed: true
      }
    ];

    const mockAnnotations = [
      {
        uid: 'ann1',
        annotation_type: 'title',
        content: 'Research Paper Title',
        confidence: 0.95,
        page_number: 1
      },
      {
        uid: 'ann2',
        annotation_type: 'author',
        content: 'John Doe',
        confidence: 0.90,
        page_number: 1
      },
      {
        uid: 'ann3',
        annotation_type: 'number',
        content: '42',
        confidence: 0.85,
        page_number: 2
      }
    ];

    (fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDocuments
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAnnotations
      });

    render(<Data_extraction />);
    
    await waitFor(() => {
      expect(screen.getByText('test1.pdf')).toBeInTheDocument();
    });

    const documentItem = screen.getByText('test1.pdf').closest('div');
    fireEvent.click(documentItem!);
    
    await waitFor(() => {
      expect(screen.getByText('Research Paper Title')).toBeInTheDocument();
      expect(screen.getByText('John Doe')).toBeInTheDocument();
      expect(screen.getByText('42')).toBeInTheDocument();
    });
  });

  test('показывает ошибки загрузки', async () => {
    (fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));

    render(<Data_extraction />);
    
    const file = new File(['test pdf content'], 'test.pdf', { type: 'application/pdf' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    
    fireEvent.change(fileInput, { target: { files: [file] } });
    
    await waitFor(() => {
      expect(screen.getByText('Ошибка загрузки файла')).toBeInTheDocument();
    });
  });

  test('показывает состояние загрузки', async () => {
    (fetch as jest.Mock).mockImplementationOnce(() => 
      new Promise(resolve => setTimeout(() => resolve({
        ok: true,
        json: async () => ({ success: true, document_id: 'test-id' })
      }), 100))
    );

    render(<Data_extraction />);
    
    const file = new File(['test pdf content'], 'test.pdf', { type: 'application/pdf' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    
    fireEvent.change(fileInput, { target: { files: [file] } });
    
    expect(screen.getByText('Загрузка файла...')).toBeInTheDocument();
  });
});
