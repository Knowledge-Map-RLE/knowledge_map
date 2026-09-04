import type { FeedbackMessage, FeedbackTicket, FeedbackStatus } from '../../services/api/feedback';

export type { FeedbackTicket, FeedbackMessage, FeedbackStatus };

export interface FeedbackChatState {
    isOpen: boolean;
    isMinimized: boolean;
    ticket: FeedbackTicket | null;
    messages: FeedbackMessage[];
    draftText: string;
    pendingImages: PendingImage[];
    sending: boolean;
    loadingMessages: boolean;
}

export interface PendingImage {
    id: string;
    file: File;
    preview: string;
    s3Key?: string;
    uploading: boolean;
}
