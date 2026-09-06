import { extend } from '@pixi/react';
import { Text, type TextOptions } from 'pixi.js';

extend({ Text });

export type PixiTextProps = Partial<TextOptions>;

export function PixiText(props: PixiTextProps) {
  const { resolution, ...rest } = props as any;
  return (
    // Типизация интринсика <pixiText> сломана в @pixi/react 8.0.2:
    // ConstructorOptions<typeof Text> резолвится в TextString (поле toString),
    // поэтому text/style/x/y/anchor отсутствуют в пропсах. Спред через any.
    // resolution=2 удваивает разрешение текстовой текстуры -> текст без размытия.
    <pixiText {...(rest as any)} resolution={resolution ?? 2} />
  );
}
