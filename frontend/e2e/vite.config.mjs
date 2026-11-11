import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Puerto y backend exclusivos para las pruebas, separados de Docker.
export default defineConfig({
  root: process.cwd(), plugins: [react()], cacheDir: './node_modules/.vite-e2e',
  server: { host: '127.0.0.1', port: 18548, strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:18547', changeOrigin: true } } },
});
