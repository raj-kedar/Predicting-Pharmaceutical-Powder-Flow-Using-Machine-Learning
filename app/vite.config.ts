import { resolve } from 'node:path';
import { defineConfig } from 'vite';

const API = process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000';
const API_PATHS = ['/auth', '/users', '/classify', '/samples', '/materials', '/predictions',
  '/audit', '/health', '/ready', '/model-card', '/billing', '/admin/'];

export default defineConfig({
  esbuild: { jsx: 'automatic', jsxImportSource: 'preact' },
  build: {
    target: 'es2020', cssCodeSplit: true, sourcemap: false,
    rollupOptions: { input: { main: resolve(__dirname, 'index.html'), admin: resolve(__dirname, 'admin.html') } },
  },
  server: { proxy: Object.fromEntries(API_PATHS.map((path) => [path, API])) },
});
