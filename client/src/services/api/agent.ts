import { withBase, authHeaders } from './http';

export interface AgentModel {
  id: string;
  provider?: string;
  configured?: boolean;
  context_length?: number;
}

export interface AgentMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

/**
 * Грубая оценка количества токенов в тексте (английский ≈ 1.3–1.4 токена/слово).
 * Используется только для индикатора «заполнено / максимум» в чате.
 */
export function estimateTokens(text: string): number {
  if (!text) return 0;
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return Math.ceil(words * 1.35);
}

/**
 * Load models exposed by the AI agent microservice (`GET /ai/v1/models`).
 */
export async function getAgentModels(): Promise<AgentModel[]> {
  const response = await fetch(withBase('/ai/v1/models'), { headers: authHeaders() });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} ${response.statusText}`);
  }
  const data = await response.json();
  return Array.isArray(data?.data) ? data.data : [];
}

export interface AgentUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface StreamAgentChatOptions {
  messages: AgentMessage[];
  model?: string;
  signal?: AbortSignal;
  onChunk: (text: string) => void;
  onUsage?: (usage: AgentUsage) => void;
  onDone: () => void;
  onError: (error: Error) => void;
}

/**
 * Stream a chat completion from the AI agent microservice (`POST /ai/v1/chat/completions`).
 */
export async function streamAgentChat(opts: StreamAgentChatOptions): Promise<void> {
  const { messages, model, signal, onChunk, onUsage, onDone, onError } = opts;
  try {
    const response = await fetch(withBase('/ai/v1/chat/completions'), {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        model: model || undefined,
        messages,
        stream: true,
        stream_options: { include_usage: true },
      }),
      signal,
    });
    if (!response.ok || !response.body) {
      const text = await response.text().catch(() => '');
      throw new Error(
        `HTTP ${response.status} ${response.statusText}${text ? `: ${text.slice(0, 300)}` : ''}`,
      );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        const data = trimmed.slice(5).trim();
        if (!data || data === '[DONE]') continue;
        try {
          const json = JSON.parse(data);
          const usage = json?.usage;
          if (usage && typeof usage.total_tokens === 'number' && onUsage) {
            onUsage({
              prompt_tokens: usage.prompt_tokens ?? 0,
              completion_tokens: usage.completion_tokens ?? 0,
              total_tokens: usage.total_tokens ?? 0,
            });
          }
          const delta = json?.choices?.[0]?.delta?.content ?? '';
          if (delta) onChunk(delta);
        } catch {
          // Ignore partial / non-JSON SSE frames.
        }
      }
    }

    onDone();
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      onDone();
      return;
    }
    onError(error instanceof Error ? error : new Error(String(error)));
  }
}
