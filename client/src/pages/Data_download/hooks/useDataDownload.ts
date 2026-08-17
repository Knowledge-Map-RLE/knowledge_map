import { useState, useEffect, useCallback, useRef } from "react";
import type { DataSourceStatus, WebSocketMessage } from "../model";

const API_BASE = "/api/data_download";
const WS_URL = `ws://${window.location.host}/api/data_download/ws`;

interface UseDataDownloadReturn {
    sources: DataSourceStatus[];
    loading: boolean;
    error: string | null;
    isConnected: boolean;
    startDownload: (source: string) => Promise<void>;
    pauseDownload: (source: string) => Promise<void>;
    resetDownload: (source: string) => Promise<void>;
    refresh: () => Promise<void>;
}

export function useDataDownload(): UseDataDownloadReturn {
    const [sources, setSources] = useState<DataSourceStatus[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const isConnectingRef = useRef(false);
    const isFirstConnectionRef = useRef(true);

    const fetchSources = useCallback(async () => {
        try {
            const response = await fetch(`${API_BASE}/sources`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            setSources(data);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to fetch sources");
        } finally {
            setLoading(false);
        }
    }, []);

    const handleWebSocketMessage = useCallback((message: WebSocketMessage) => {
        switch (message.type) {
            case "progress":
                setSources((prev) =>
                    prev.map((src) =>
                        src.name === message.source
                            ? {
                                  ...src,
                                  downloaded_files: message.downloaded ?? src.downloaded_files,
                                  total_files: message.total ?? src.total_files,
                                  progress_percent: message.percent ?? src.progress_percent,
                                  status: message.status ?? src.status,
                                  current_file: message.current_file ?? src.current_file,
                                  processed_files: message.processed_files ?? src.processed_files,
                                  processing_total: message.processing_total ?? src.processing_total,
                                  processing_percent: message.processing_percent ?? src.processing_percent,
                                  processing_current_file: message.processing_current_file ?? src.processing_current_file,
                              }
                            : src
                    )
                );
                break;
            case "status_change":
                setSources((prev) =>
                    prev.map((src) =>
                        src.name === message.source
                            ? { ...src, status: message.status }
                            : src
                    )
                );
                break;
            case "error":
                setSources((prev) =>
                    prev.map((src) =>
                        src.name === message.source
                            ? { ...src, status: "error", error_message: message.error }
                            : src
                    )
                );
                break;
            case "connected":
                console.log("Received connected message");
                break;
        }
    }, []);

    const connectWebSocket = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN || isConnectingRef.current) {
            return;
        }

        isConnectingRef.current = true;

        const doConnect = () => {
            const ws = new WebSocket(WS_URL);

            ws.onopen = () => {
                isConnectingRef.current = false;
                isFirstConnectionRef.current = false;
                setIsConnected(true);
                console.log("WebSocket connected");
            };

            ws.onmessage = (event) => {
                try {
                    const message: WebSocketMessage = JSON.parse(event.data);
                    handleWebSocketMessage(message);
                } catch (err) {
                    console.error("Failed to parse WebSocket message:", err);
                }
            };

            ws.onclose = () => {
                isConnectingRef.current = false;
                setIsConnected(false);
                console.log("WebSocket disconnected, reconnecting...");
                reconnectTimeoutRef.current = setTimeout(() => {
                    connectWebSocket();
                }, 3000);
            };

            ws.onerror = (err) => {
                isConnectingRef.current = false;
                console.error("WebSocket error:", err);
            };

            wsRef.current = ws;
        };

        if (isFirstConnectionRef.current) {
            setTimeout(doConnect, 2000);
        } else {
            doConnect();
        }
    }, [handleWebSocketMessage]);

    const sendAction = useCallback(async (action: string, source: string) => {
        try {
            const response = await fetch(`${API_BASE}/${action}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ source }),
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : `Failed to ${action}`);
        }
    }, []);

    const startDownload = useCallback(
        async (source: string) => {
            await sendAction("start", source);
        },
        [sendAction]
    );

    const pauseDownload = useCallback(
        async (source: string) => {
            await sendAction("pause", source);
        },
        [sendAction]
    );

    const resetDownload = useCallback(
        async (source: string) => {
            await sendAction("reset", source);
        },
        [sendAction]
    );

    const refresh = useCallback(async () => {
        await fetchSources();
    }, [fetchSources]);

    useEffect(() => {
        fetchSources();
        connectWebSocket();

        const pollInterval = setInterval(() => {
            fetchSources();
        }, 15000);

        return () => {
            clearInterval(pollInterval);
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, [fetchSources, connectWebSocket]);

    return {
        sources,
        loading,
        error,
        isConnected,
        startDownload,
        pauseDownload,
        resetDownload,
        refresh,
    };
}