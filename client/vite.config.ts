/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    server: {
      deps: {
        inline: [/@pixi\/react/, /react-reconciler/],
      },
    },
  },
  server: {
    host: true,
    port: 5555,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        ws: true,
      },
      '/ai': {
        target: 'http://localhost:50059',
        ws: true,
      },
      '/billing': {
        target: 'http://localhost:50058',
        ws: false,
      },
    },
  },
  worker: {
    format: 'es',
  },
})
