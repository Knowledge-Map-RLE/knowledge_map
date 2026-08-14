import { fetchJson, authHeaders, withBase } from './http';

export interface AIChatSummary {
  id: string;
  title: string;
  model: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AIChatCostBreakdown {
  input: string;
  cached: string;
  output: string;
  tool: string;
}

export interface AIChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at?: string | null;
  tokens?: number | null;
  cost?: string | null;
  input_tokens?: number | null;
  cached_tokens?: number | null;
  tool_tokens?: number | null;
  total_tokens?: number | null;
  cost_breakdown?: AIChatCostBreakdown | null;
  cache_used?: boolean;
}

export interface AIChatEstimate {
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_cached_tokens: number | null;
  estimated_cost: string;
  estimated_max_cost: string;
  cost_breakdown?: AIChatCostBreakdown | null;
  currency: string;
  is_estimate: boolean;
}

export interface AIUsageSummary {
  period: string;
  input_tokens: number;
  cached_tokens: number;
  output_tokens: number;
  tool_tokens: number;
  total_tokens: number;
  cost: string;
  currency: string;
  request_count: number;
}

export interface AIChatStreamOptions {
  content: string;
  signal?: AbortSignal;
  onChunk: (text: string) => void;
  onUsage?: (usage: AIChatStreamUsage) => void;
  onDone: () => void;
  onError: (error: Error) => void;
}

export interface AIChatStreamUsage {
  message_uid: string;
  prompt_tokens: number;
  cached_tokens: number;
  completion_tokens: number;
  tool_tokens: number;
  total_tokens: number;
  cost: string;
  cost_breakdown?: AIChatCostBreakdown | null;
  currency: string;
  deducted: boolean;
  deduct_error: string | null;
}

export async function listAIChats(limit = 50): Promise<AIChatSummary[]> {
  const data = await fetchJson<{ chats: AIChatSummary[] }>(`/api/ai/chats?limit=${limit}`);
  return data.chats ?? [];
}

export async function createAIChat(title = ''): Promise<AIChatSummary> {
  return fetchJson<AIChatSummary>('/api/ai/chats', {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export async function getAIChatMessages(chatId: string, limit = 100): Promise<AIChatMessage[]> {
  const data = await fetchJson<{ messages: AIChatMessage[] }>(
    `/api/ai/chats/${encodeURIComponent(chatId)}/messages?limit=${limit}`,
  );
  return data.messages ?? [];
}

export async function estimateAIChatMessage(
  chatId: string,
  messages: { role: string; content: string }[],
  maxOutputTokens?: number,
): Promise<AIChatEstimate> {
  return fetchJson<AIChatEstimate>(`/api/ai/chats/${encodeURIComponent(chatId)}/messages/estimate`, {
    method: 'POST',
    body: JSON.stringify({ messages, max_output_tokens: maxOutputTokens }),
  });
}

export async function getAIUsageSummary(period: 'current' | 'previous' = 'current'): Promise<AIUsageSummary> {
  return fetchJson<AIUsageSummary>(`/api/ai/usage/summary?period=${period}`);
}

/**
 * Потоковая отправка сообщения в серверный AI-чат (SSE через `/api/ai/chats/{id}/messages`).
 */
export async function streamAIChatMessage(chatId: string, opts: AIChatStreamOptions): Promise<void> {
  const { content, signal, onChunk, onUsage, onDone, onError } = opts;
  try {
    const response = await fetch(withBase(`/api/ai/chats/${encodeURIComponent(chatId)}/messages`), {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ content }),
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
          const event = JSON.parse(data);
          if (event.type === 'chunk' && typeof event.content === 'string') {
            onChunk(event.content);
          } else if (event.type === 'usage' && onUsage) {
            onUsage(event as AIChatStreamUsage);
          } else if (event.type === 'error') {
            throw new Error(event.message || 'AI gateway error');
          }
        } catch (err) {
          if (err instanceof Error && !(err instanceof DOMException)) {
            onError(err);
            return;
          }
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
