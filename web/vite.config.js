import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
const apiProxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api/, ''),
  },
}

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    proxy: apiProxy,
  },
  preview: {
    host: true,
    proxy: apiProxy,
  },
})
