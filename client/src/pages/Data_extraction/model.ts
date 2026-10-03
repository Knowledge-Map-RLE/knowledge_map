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
    is_gold_standard?: boolean;
    gold_standard_source_pmc_id?: string;
    current_user_last_edited_at?: string | null;
}

export type DataExtractionTab = 'pdf' | 'markdown' | 'annotator' | 'chat';
export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';
