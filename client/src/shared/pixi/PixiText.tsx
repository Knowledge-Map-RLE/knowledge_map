import { extend } from '@pixi/react';
import { Text, type TextOptions } from 'pixi.js';

extend({ Text });

export type PixiTextProps = Partial<TextOptions>;

export function PixiText(props: PixiTextProps) {
  return (
    // Типизация интринсика <pixiText> сломана в @pixi/react 8.0.2:
    // ConstructorOptions<typeof Text> резолвится в TextString (поле toString),
    // поэтому text/style/x/y/anchor отсутствуют в пропсах. Спред через any.
    <pixiText {...(props as any)} />
  );
}
