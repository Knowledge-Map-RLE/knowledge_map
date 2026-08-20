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
    source?: string;
    pubmed_id?: string;
    pmc_id?: string;
    doi?: string;
}

export type DataExtractionTab = 'pdf' | 'markdown' | 'annotator' | 'patterns' | 'linguistic-graph' | 'graph' | 'chat';
export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';
