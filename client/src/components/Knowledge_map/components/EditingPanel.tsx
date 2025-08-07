import React from 'react';
import type { BlockData } from '../types';

interface EditingPanelProps {
  editingBlock: BlockData | null;
  creatingBlock: {
    sourceBlock: BlockData | null;
    targetLevel: number;
  } | null;
  editingText: string;
  setEditingText: (text: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onCreateNewBlock: () => void;
}

export const EditingPanel: React.FC<EditingPanelProps> = ({
  editingBlock,
  creatingBlock,
  editingText,
  setEditingText,
  onSaveEdit,
  onCancelEdit,
  onCreateNewBlock
}) => {
  if (!editingBlock && !creatingBlock) {
    return null;
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-white border-t-2 border-blue-500 shadow-lg z-50 p-4">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center space-x-4">
          <div className="flex-shrink-0">
            <h3 className="text-lg font-semibold text-gray-800">
              {editingBlock ? 'Редактировать блок' : 'Создать новый блок'}
            </h3>
          </div>
          <div className="flex-1">
            <textarea
              value={editingText}
              onChange={(e) => setEditingText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && e.shiftKey) {
                  e.preventDefault();
                  if (editingBlock) {
                    onSaveEdit();
                  } else if (creatingBlock) {
                    onCreateNewBlock();
                  }
                } else if (e.key === 'Escape') {
                  e.preventDefault();
                  onCancelEdit();
                }
              }}
              className="w-full h-20 p-3 border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder={editingBlock ? "Введите текст блока..." : "Введите текст нового блока..."}
              autoFocus
            />
          </div>
          <div className="flex-shrink-0 flex items-center space-x-3">
            <div className="text-sm text-gray-500">
              Shift+Enter - сохранить, Esc - отменить
            </div>
            <button
              onClick={onCancelEdit}
              className="px-4 py-2 text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Отменить
            </button>
            <button
              onClick={editingBlock ? onSaveEdit : onCreateNewBlock}
              className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600"
            >
              {editingBlock ? 'Сохранить' : 'Создать'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}; 