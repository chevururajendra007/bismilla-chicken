import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Locally the FastAPI server runs on :8000 (uvicorn main:app --reload)
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
