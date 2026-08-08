import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // The production gateway mounts the widget under /widget/. Without an
  // explicit base Vite emits root-level asset URLs that are served by the
  // admin application instead of the widget container. Standalone hosts such
  // as Vercel override this with VITE_BASE_PATH=/ at build time.
  base: process.env.VITE_BASE_PATH || '/widget/',
  plugins: [react({ jsxImportSource: '@emotion/react', babel: { plugins: ['@emotion/babel-plugin'] } })],
  server: { port: 5173 },
  preview: { port: 5174 },
  build: {
    manifest: true
  }
})
