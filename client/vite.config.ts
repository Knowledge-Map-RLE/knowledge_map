import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    host: true,
    port: 5555,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        ws: true,
      },
      '/ai': {
        target: 'http://localhost:50054',
        ws: true,
      },
    },
  },
  worker: {
    format: 'es',
  },
})
