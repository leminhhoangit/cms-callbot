/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// build ra ../app/static – FastAPI phục vụ luôn, máy chạy CMS không cần Node
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../app/static', emptyOutDir: true, chunkSizeWarningLimit: 2000 },
  server: { proxy: { '/api': 'http://127.0.0.1:8780' } },
  test: { environment: 'jsdom', setupFiles: ['./src/setup.ts'], globals: true, testTimeout: 30000 },
})
