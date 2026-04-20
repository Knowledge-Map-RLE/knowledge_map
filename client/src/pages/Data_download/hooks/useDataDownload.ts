import { useState, useEffect, useCallback, useRef } from "react";
import { DataSourceStatus, WebSocketMessage, DownloadAction } from "../model";

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
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
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
    }, []);

    const handleWebSocketMessage = useCallback((message: WebSocketMessage) => {
        switch (message.type) {
            case "progress":
            case "status_change":
            case "error":
                setSources((prev) =>
                    prev.map((src) =>
                        src.name === message.source
                            ? {
                                  ...src,
                                  downloaded_files: "downloaded" in message ? message.downloaded : src.downloaded_files,
                                  total_files: "total" in message ? message.total : src.total_files,
                                  progress_percent: "percent" in message ? message.percent : src.progress_percent,
                                  status: message.status,
                              }
                            : src
                    )
                );
                break;
            case "connected":
                console.log("Received connected message");
                break;
        }
    }, []);

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

        return () => {
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