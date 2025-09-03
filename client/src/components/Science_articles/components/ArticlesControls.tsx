import ModeIndicator from '../../Knowledge_map/ModeIndicator';
import { EditingPanel } from '../../Knowledge_map/components/EditingPanel';
import { BlockContextMenu } from '../../Knowledge_map/BlockContextMenu';
import type { BlockData } from '../../Knowledge_map/types';
import type { EditMode } from '../../Knowledge_map/types';

interface ArticlesControlsProps {
  currentMode: EditMode;
  linkCreationStep: string;
  editingBlock: string | null;
  creatingBlock: any;
  editingText: string;
  contextMenu: any;
  blocks: BlockData[];
  setEditingText: (text: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onCreateNewBlock: () => void;
  onPin: () => void;
  onUnpin: () => void;
  onPinWithScale: (scale: number) => void;
  onCloseContextMenu: () => void;
}

export function ArticlesControls({
  currentMode,
  linkCreationStep,
  editingBlock,
  creatingBlock,
  editingText,
  contextMenu,
  blocks,
  setEditingText,
  onSaveEdit,
  onCancelEdit,
  onCreateNewBlock,
  onPin,
  onUnpin,
  onPinWithScale,
  onCloseContextMenu
}: ArticlesControlsProps) {
  return (
    <>
      <ModeIndicator currentMode={currentMode} linkCreationStep={linkCreationStep} />

      {/* Панель редактирования/создания блоков */}
      <EditingPanel
        editingBlock={editingBlock}
        creatingBlock={creatingBlock}
        editingText={editingText}
        setEditingText={setEditingText}
        onSaveEdit={onSaveEdit}
        onCancelEdit={onCancelEdit}
        onCreateNewBlock={onCreateNewBlock}
      />

      {/* Контекстное меню */}
      {contextMenu && (
        <BlockContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          isPinned={blocks.find(b => b.id === contextMenu.blockId)?.is_pinned || false}
          currentPhysicalScale={blocks.find(b => b.id === contextMenu.blockId)?.physical_scale || 0}
          onPin={onPin}
          onUnpin={onUnpin}
          onPinWithScale={onPinWithScale}
          onClose={onCloseContextMenu}
        />
      )}
    </>
  );
}
