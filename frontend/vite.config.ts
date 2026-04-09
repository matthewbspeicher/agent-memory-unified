import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          // Vendor chunks for heavy dependencies
          if (id.includes('node_modules')) {
            if (id.includes('3d-force-graph')) {
              return 'vendor-3d-graph';
            }
            if (id.includes('@tanstack')) {
              return 'vendor-query';
            }
            if (id.includes('react-dom')) {
              return 'vendor-react';
            }
          }
        },
      },
    },
    chunkSizeWarningLimit: 500,
  },
  server: {
    port: 3000,
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        ws: true
      },
      '/engine/v1': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        ws: true
      },
      '/engine/v1/ws': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        ws: true
      }
    }
  }
})
