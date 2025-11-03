import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): State {
    // Обновляем состояние, чтобы следующий рендер показал запасной UI
    return {
      hasError: true,
      error,
      errorInfo: null,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Логируем ошибку
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.setState({
      error,
      errorInfo,
    });
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  render() {
    if (this.state.hasError) {
      // Если предоставлен пользовательский fallback, используем его
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Иначе показываем стандартный UI ошибки
      return (
        <div
          style={{
            padding: '20px',
            margin: '20px',
            border: '2px solid #f44336',
            borderRadius: '8px',
            backgroundColor: '#ffebee',
          }}
        >
          <h2 style={{ color: '#c62828', marginTop: 0 }}>Произошла ошибка</h2>
          <p style={{ color: '#c62828' }}>
            Что-то пошло не так. Попробуйте обновить страницу или вернуться назад.
          </p>

          <details style={{ marginTop: '16px', cursor: 'pointer' }}>
            <summary style={{ fontWeight: 'bold', marginBottom: '8px' }}>
              Детали ошибки (для разработчиков)
            </summary>
            <pre
              style={{
                padding: '12px',
                backgroundColor: '#fff',
                border: '1px solid #ddd',
                borderRadius: '4px',
                overflow: 'auto',
                fontSize: '12px',
                marginTop: '8px',
              }}
            >
              {this.state.error && this.state.error.toString()}
              {'\n\n'}
              {this.state.errorInfo && this.state.errorInfo.componentStack}
            </pre>
          </details>

          <div style={{ marginTop: '16px', display: 'flex', gap: '8px' }}>
            <button
              onClick={this.handleReset}
              style={{
                padding: '8px 16px',
                backgroundColor: '#2196f3',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              Попробовать снова
            </button>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding: '8px 16px',
                backgroundColor: '#4caf50',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              Обновить страницу
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
