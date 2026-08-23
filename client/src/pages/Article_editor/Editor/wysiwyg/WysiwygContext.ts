import { createContext, useContext } from 'react';
import type React from 'react';
import type { BlockDataValue } from '../../model';

export interface UuidRef {
    id: string;
    label: string;
    chainText?: string;
    blockType?: number;
}

export interface FieldKeyInfo {
    lineId: string;
    fieldKey: string;
    multiline: boolean;
}

export interface WysiwygApi {
    setField: (lineId: string, fieldKey: string, value: BlockDataValue) => void;
    requestFocus: (lineId: string, fieldKey?: string) => void;
    insertBelow: (lineId: string, typeNumber?: number) => void;
    removeLine: (lineId: string) => void;
    duplicateLine: (lineId: string) => void;
    moveLine: (lineId: string, delta: -1 | 1) => void;
    jumpToLine: (lineId: string) => void;
    openSlashMenu: (anchor: { lineId: string; fieldKey: string; rect: DOMRect | null }) => void;
    fieldKeyDown: (e: React.KeyboardEvent<HTMLElement>, info: FieldKeyInfo) => void;
    beginFieldEdit: (lineId: string, fieldKey: string) => void;
    appendChildLine: (parentLineId: string, fieldKey: string) => void;
    refs: UuidRef[];
    showUids: boolean;
    onUploadImage?: (key: string, file: File) => Promise<string>;
}

export const WysiwygApiContext = createContext<WysiwygApi | null>(null);

export function useWysiwygApi(): WysiwygApi {
    const api = useContext(WysiwygApiContext);
    if (!api) throw new Error('WysiwygApiContext is not mounted');
    return api;
}
