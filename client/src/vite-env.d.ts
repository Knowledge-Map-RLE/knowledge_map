/// <reference types="vite/client" />

interface ImportMetaEnv {
    readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}

import { PixiReactElementProps } from '@pixi/react';
import { Graphics, Container } from 'pixi.js';

declare module '@pixi/react' {
  interface PixiElements {
    graphics: PixiReactElementProps<typeof Graphics>;
    container: PixiReactElementProps<typeof Container>;
  }
}

declare module '*.module.css' {
  const classes: { [key: string]: string };
  export default classes;
}
