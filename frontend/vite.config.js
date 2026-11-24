import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Locally the FastAPI server runs on :8000 (uvicorn main:app --reload)
// Preact (10 KB) stands in for React (130 KB) – same components, much lighter for budget phones.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      react: 'preact/compat',
      'react-dom/client': 'preact/compat/client',
      'react-dom': 'preact/compat',
      'react/jsx-runtime': 'preact/jsx-runtime',
      'react/jsx-dev-runtime': 'preact/jsx-dev-runtime',
    },
  },
  server: { proxy: { '/api': 'http://localhost:8000' } },
  preview: { proxy: { '/api': 'http://localhost:8000' } },
})
