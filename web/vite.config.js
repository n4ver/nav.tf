import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const commandTarget = env.VITE_COMMAND_PROXY_TARGET || 'http://127.0.0.1:8001'
  const queryTarget = env.VITE_QUERY_PROXY_TARGET || 'http://127.0.0.1:8002'

  const apiProxy = {
    '/api/v1/auth': {
      target: commandTarget,
      changeOrigin: true,
      xfwd: true,
    },
    '/api/v1/commands': {
      target: commandTarget,
      changeOrigin: true,
      xfwd: true,
    },
    '/api/v1/queries': {
      target: queryTarget,
      changeOrigin: true,
      xfwd: true,
    },
    // Health checks hit whichever service is up; prefer query for reads.
    '/health': {
      target: queryTarget,
      changeOrigin: true,
    },
  }

  return {
    plugins: [vue(), tailwindcss()],
    server: {
      host: true,
      proxy: apiProxy,
    },
    preview: {
      host: true,
      proxy: apiProxy,
    },
    test: {
      environment: 'happy-dom',
      globals: true,
      setupFiles: ['./src/test/setup.js'],
    },
  }
})
