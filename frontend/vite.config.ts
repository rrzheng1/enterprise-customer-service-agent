import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'BACKEND_');
  const target = env.BACKEND_URL || process.env.BACKEND_URL || 'http://127.0.0.1:8002';
  return {
    plugins: [react(), tailwindcss()],
    server: { port: 5173, strictPort: true, proxy: Object.fromEntries(
      ['/api', '/ops/api', '/health', '/ui/config', '/demo/legacy', '/ops'].map(path => [path, { target, changeOrigin: true }]),
    ) },
    build: { outDir: 'dist', sourcemap: false },
  };
});
