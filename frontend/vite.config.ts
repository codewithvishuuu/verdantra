import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev proxy keeps API.md base URL (localhost:8000) working from :5173.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/media': 'http://localhost:8000',
      '/healthz': 'http://localhost:8000',
    },
  },
});
