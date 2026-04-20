export interface DataSourceStatus {
    name: string;
    ftp_url: string;
    description?: string;
    total_files: number;
    downloaded_files: number;
    progress_percent: number;
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
    | "completed"
    | "error";

export interface DownloadAction {
    source: string;
}

export interface ProgressMessage {
    type: "progress";
    source: string;
    downloaded: number;
    total: number;
    percent: number;
    status: DataSourceState;
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