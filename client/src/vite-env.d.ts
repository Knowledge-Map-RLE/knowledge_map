/// <reference types="vite/client" />

import { PixiReactElementProps } from '@pixi/react';
import { Graphics, Container } from 'pixi.js';

declare module '@pixi/react' {
  interface PixiElements {
    graphics: PixiReactElementProps<typeof Graphics>;
    container: PixiReactElementProps<typeof Container>;
  }
}
