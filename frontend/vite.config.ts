import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// El backend sirve /api, /auth y /ws. En dev se hace proxy hacia uvicorn para
// trabajar en el mismo origen que en producción y evitar CORS.
const BACKEND = process.env.DFT_MONITOR_BACKEND ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  build: {
    // El SPA compilado lo sirve FastAPI desde src/monitor_api/static.
    outDir: path.resolve(__dirname, '../src/monitor_api/static'),
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/auth': { target: BACKEND, changeOrigin: true },
      '/ws': { target: BACKEND.replace(/^http/, 'ws'), ws: true },
    },
  },
})
