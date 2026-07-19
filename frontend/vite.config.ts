import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Served under /app in prod (FastAPI StaticFiles mount). Dev server proxies the
// backend API + WebSocket so the SPA talks to :8001 without CORS.
export default defineConfig({
  base: '/app/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8001',
      '/health': 'http://localhost:8001',
      '/ws': { target: 'ws://localhost:8001', ws: true },
    },
  },
  build: { outDir: 'dist' },
})
