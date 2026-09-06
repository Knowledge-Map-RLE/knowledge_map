import { useState, useEffect, useCallback, useRef } from "react";
import type { CitationSourceStatus, CitationSourceState, CitationTestResult, LoadOneResult } from "../model";

const API_BASE = "/api/citation_graph";
const WS_URL = `ws://${window.location.host}/api/data_download/ws`;

interface UseCitationDownloadReturn {
    sources: CitationSourceStatus[];
    loading: boolean;
    error: string | null;
    isConnected: boolean;
    startLoad: (key: string, maxFiles?: number) => Promise<void>;
    pauseLoad: (key: string) => Promise<void>;
    resumeLoad: (key: string) => Promise<void>;
    resetLoad: (key: string) => Promise<void>;
    testSource: (key: string) => Promise<CitationTestResult | null>;
    loadByDoi: (doi: string) => Promise<LoadOneResult | null>;
    refresh: () => Promise<void>;
}

export function useCitationDownload(): UseCitationDownloadReturn {
    const [sources, setSources] = useState<CitationSourceStatus[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const isConnectingRef = useRef(false);
    const initializingRef = useRef(false);

    const fetchSources = useCallback(async () => {
        try {
            const resp = await fetch(`${API_BASE}/sources`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            if (data.length === 0 && !initializingRef.current) {
                initializingRef.current = true;
                let initialized = false;
                try {
                    const initResp = await fetch(`${API_BASE}/initialize`, { method: "POST" });
                    initialized = initResp.ok;
                } finally {
                    initializingRef.current = false;
                }
                if (initialized) {
                    const resp2 = await fetch(`${API_BASE}/sources`);
                    if (!resp2.ok) throw new Error(`HTTP ${resp2.status}`);
                    setSources(await resp2.json());
                } else {
                    setSources(data);
                }
            } else {
                setSources(data);
            }
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to fetch sources");
        } finally {
            setLoading(false);
        }
    }, []);

    const handleWsMessage = useCallback((data: any) => {
        if (data.type === "progress" && data.source?.startsWith("citation_")) {
            const key = data.source.replace("citation_", "");
            setSources((prev) =>
                prev.map((s) =>
                    s.key === key
                        ? {
                              ...s,
                              downloaded_edges: data.downloaded ?? s.downloaded_edges,
                              total_edges: data.total ?? s.total_edges,
                              progress_percent: data.percent ?? s.progress_percent,
                              status: (data.status ?? s.status) as CitationSourceState,
                          }
                        : s
                )
            );
        }
        if (data.type === "status_change" && data.source?.startsWith("citation_")) {
            const key = data.source.replace("citation_", "");
            setSources((prev) =>
                prev.map((s) =>
                    s.key === key
                        ? { ...s, status: data.status as CitationSourceState }
                        : s
                )
            );
        }
        if (data.type === "error" && data.source?.startsWith("citation_")) {
            const key = data.source.replace("citation_", "");
            setSources((prev) =>
                prev.map((s) =>
                    s.key === key
                        ? { ...s, status: "error", error_message: data.error }
                        : s
                )
            );
        }
    }, []);

    const connectWebSocket = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN || isConnectingRef.current) return;
        isConnectingRef.current = true;
        const ws = new WebSocket(WS_URL);
        ws.onopen = () => { isConnectingRef.current = false; setIsConnected(true); };
        ws.onmessage = (e) => {
            try { handleWsMessage(JSON.parse(e.data)); } catch {}
        };
        ws.onclose = () => {
            isConnectingRef.current = false;
            setIsConnected(false);
            reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000);
        };
        ws.onerror = () => { isConnectingRef.current = false; };
        wsRef.current = ws;
    }, [handleWsMessage]);

    const startLoad = useCallback(async (key: string, maxFiles?: number) => {
        try {
            const qs = new URLSearchParams();
            if (maxFiles !== undefined && maxFiles > 0) {
                qs.set("max_files", String(maxFiles));
            }
            const suffix = qs.toString();
            await fetch(`${API_BASE}/load/${key}${suffix ? `?${suffix}` : ""}`, { method: "POST" });
            await fetchSources();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to start load");
        }
    }, [fetchSources]);

    const pauseLoad = useCallback(async (key: string) => {
        try {
            await fetch(`${API_BASE}/pause/${key}`, { method: "POST" });
            setSources((prev) =>
                prev.map((s) => (s.key === key ? { ...s, status: "paused" as CitationSourceState } : s))
            );
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to pause");
        }
    }, []);

    const resumeLoad = useCallback(async (key: string) => {
        try {
            await fetch(`${API_BASE}/resume/${key}`, { method: "POST" });
            setSources((prev) =>
                prev.map((s) => (s.key === key ? { ...s, status: "downloading" as CitationSourceState } : s))
            );
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to resume");
        }
    }, []);

    const resetLoad = useCallback(async (key: string) => {
        try {
            await fetch(`${API_BASE}/reset/${key}`, { method: "POST" });
            await fetchSources();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to reset");
        }
    }, [fetchSources]);

    const testSource = useCallback(async (key: string): Promise<CitationTestResult | null> => {
        try {
            const resp = await fetch(`${API_BASE}/test/${key}?sample_size=10`, { method: "POST" });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            return await resp.json();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Test failed");
            return null;
        }
    }, []);

    const loadByDoi = useCallback(async (doi: string): Promise<LoadOneResult | null> => {
        try {
            const resp = await fetch(`${API_BASE}/load_one`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ doi }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            return await resp.json();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Load by DOI failed");
            return null;
        }
    }, []);

    const refresh = useCallback(async () => {
        await fetchSources();
    }, [fetchSources]);

    useEffect(() => {
        fetchSources();
        connectWebSocket();
        const interval = setInterval(fetchSources, 15000);
        return () => {
            clearInterval(interval);
            if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
            wsRef.current?.close();
        };
    }, [fetchSources, connectWebSocket]);

    return { sources, loading, error, isConnected, startLoad, pauseLoad, resumeLoad, resetLoad, testSource, loadByDoi, refresh };
}
