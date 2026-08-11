export interface PDFDocument {
    uid: string;
    original_filename: string;
    md5_hash: string;
    file_size?: number;
    upload_date: string;
    title?: string;
    authors?: string[];
    abstract?: string;
    keywords?: string[];
    processing_status: string;
    is_processed: boolean;
    pdf_url?: string;
}

export type DataExtractionTab = 'pdf' | 'markdown' | 'annotator' | 'patterns' | 'linguistic-graph' | 'graph' | 'chat';
export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';
