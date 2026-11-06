import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Only proxy through Nginx when explicitly configured (Docker sets this).
  // Local `npm run dev` defaults to direct command/query service ports.
  const gatewayTarget = env.VITE_GATEWAY_PROXY_TARGET
  const commandTarget = env.VITE_COMMAND_PROXY_TARGET || 'http://127.0.0.1:8001'
  const queryTarget = env.VITE_QUERY_PROXY_TARGET || 'http://127.0.0.1:8002'

  const apiProxy = gatewayTarget
    ? {
        '/api/command': {
          target: gatewayTarget,
          changeOrigin: true,
          xfwd: true,
        },
        '/api/auth': {
          target: gatewayTarget,
          changeOrigin: true,
          xfwd: true,
        },
        '/api/v1/auth': {
          target: gatewayTarget,
          changeOrigin: true,
          xfwd: true,
        },
        '/api/query': {
          target: gatewayTarget,
          changeOrigin: true,
          xfwd: true,
        },
        '/health': {
          target: gatewayTarget,
          changeOrigin: true,
        },
      }
    : {
        '/api/command': {
          target: commandTarget,
          changeOrigin: true,
          xfwd: true,
          rewrite: (path) => path.replace(/^\/api\/command/, '/api/v1/commands'),
        },
        '/api/auth': {
          target: commandTarget,
          changeOrigin: true,
          xfwd: true,
          rewrite: (path) => path.replace(/^\/api\/auth/, '/api/v1/auth'),
        },
        '/api/v1/auth': {
          target: commandTarget,
          changeOrigin: true,
          xfwd: true,
        },
        '/api/query': {
          target: queryTarget,
          changeOrigin: true,
          xfwd: true,
          rewrite: (path) => path.replace(/^\/api\/query/, '/api/v1/queries'),
        },
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
