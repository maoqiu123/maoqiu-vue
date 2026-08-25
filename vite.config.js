import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import legacy from '@vitejs/plugin-legacy'
import vue2 from '@vitejs/plugin-vue2'

const rootIndexRedirect = {
  name: 'root-index-redirect',
  configureServer(server) {
    server.middlewares.use((request, response, next) => {
      if (request.url === '/' || request.url?.startsWith('/?')) {
        const query = request.url.includes('?') ? request.url.slice(request.url.indexOf('?')) : ''
        request.url = `/index.html${query}`
      }
      next()
    })
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  build: {
    // Dependencies used by the upgraded dashboard contain async generators.
    // Keep them in the modern bundle; plugin-legacy emits the fallback bundle.
    target: 'esnext',
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        discoveryLoop: fileURLToPath(new URL('./discovery-loop.html', import.meta.url))
      }
    }
  },
  plugins: [
    rootIndexRedirect,
    vue2(),
    legacy({
      renderLegacyChunks: false
    })
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  }
})
