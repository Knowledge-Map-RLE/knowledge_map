export interface DataSourceStatus {
    name: string;
    ftp_url: string;
    source_type: string;
    description?: string;
    total_files: number;
    downloaded_files: number;
    progress_percent: number;
    processed_files: number;
    processing_total: number;
    processing_percent: number;
    processing_current_file?: string;
    status: DataSourceState;
    current_file?: string;
    error_message?: string;
    last_updated?: string;
}

export type DataSourceState =
    | "idle"
    | "starting"
    | "downloading"
    | "paused"
    | "stopped"
    | "processing"
    | "completed"
    | "error";

export interface DownloadAction {
    source: string;
}

export interface ProgressMessage {
    type: "progress";
    source: string;
    downloaded?: number;
    total?: number;
    percent?: number;
    status?: DataSourceState;
    current_file?: string;
    processed_files?: number;
    processing_total?: number;
    processing_percent?: number;
    processing_current_file?: string;
}

export interface StatusChangeMessage {
    type: "status_change";
    source: string;
    status: DataSourceState;
    message?: string;
}

export interface ErrorMessage {
    type: "error";
    source: string;
    error: string;
}

export interface ConnectedMessage {
    type: "connected";
    message: string;
}

export type WebSocketMessage =
    | ProgressMessage
    | StatusChangeMessage
    | ErrorMessage
    | ConnectedMessage;

// Citation Graph types
export interface CitationSourceStatus {
    key: string;
    name: string;
    url: string;
    source_type: string;
    description?: string;
    total_edges: number;
    downloaded_edges: number;
    progress_percent: number;
    status: CitationSourceState;
    error_message?: string;
    last_updated?: string;
}

export type CitationSourceState =
    | "idle"
    | "downloading"
    | "layouting"
    | "completed"
    | "error"
    | "paused";

export interface CitationTestResult {
    source_name: string;
    sample_size: number;
    elapsed_seconds: number;
    edges_found: number;
    estimated_total_edges?: number;
    estimated_time_seconds?: number;
    errors: string[];
    success: boolean;
}

export interface LoadOneResult {
    doi: string;
    total_edges_raw: number;
    unique_edges: number;
    written_ops: number;
    sources: Record<string, { edges: number; status: string; error?: string }>;
    layout?: { success: boolean; updated: number };
}
