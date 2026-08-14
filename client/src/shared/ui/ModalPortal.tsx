import { createPortal } from 'react-dom';
import type { ReactNode } from 'react';

/**
 * Рендерит контент в document.body.
 * Нужен для модальных окон: иначе они попадают в stacking context родителя
 * (например, шапки со sticky + backdrop-filter) и контент страницы их перекрывает.
 */
export const ModalPortal: React.FC<{ children: ReactNode }> = ({ children }) => {
    return createPortal(children, document.body);
};

export default ModalPortal;
