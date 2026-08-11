import { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';
import type { ViewportRef } from '../../widgets/KnowledgeMap';

interface ViewportContextType {
    viewportRef: React.RefObject<ViewportRef | null> | null;
    setViewportRef: (ref: React.RefObject<ViewportRef | null>) => void;
}

const ViewportContext = createContext<ViewportContextType | null>(null);

export function ViewportProvider({ children }: { children: ReactNode }) {
    const [viewportRef, setViewportRef] = useState<React.RefObject<ViewportRef | null> | null>(null);

    const handleSetViewportRef = (ref: React.RefObject<ViewportRef | null>) => {
        setViewportRef(ref);
    };

    return (
        <ViewportContext.Provider value={{ viewportRef, setViewportRef: handleSetViewportRef }}>
            {children}
        </ViewportContext.Provider>
    );
}

export function useViewport() {
    const context = useContext(ViewportContext);
    if (!context) {
        console.error('useViewport must be used within a ViewportProvider');
        throw new Error('useViewport must be used within a ViewportProvider');
    }
    return context;
}
