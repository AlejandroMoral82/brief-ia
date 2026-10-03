import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, searchForWorkspaceRoot } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

const DIA = 24 * 60 * 60

// Fuente unica de categorias, compartida con el pipeline. Esta fuera de app/.
const CATEGORIAS = fileURLToPath(new URL('../categorias.json', import.meta.url))

export default defineConfig({
  base: '/brief-ia/',
  // El servidor de desarrollo solo sirve app/; se permite ademas ese fichero
  // concreto, no toda la raiz del repo.
  server: {
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), CATEGORIAS] },
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Brief IA',
        short_name: 'Brief',
        lang: 'es',
        start_url: '/brief-ia/',
        display: 'standalone',
        background_color: '#070908',
        theme_color: '#070908',
        icons: [
          { src: 'favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' },
        ],
      },
      workbox: {
        navigateFallbackDenylist: [/\/data\//],
        runtimeCaching: [{
          urlPattern: /\/data\/.*\.json$/,
          handler: 'NetworkFirst',
          options: {
            cacheName: 'brief-data',
            // Con red lenta, tras 5 s se sirve lo cacheado en vez de esperar.
            networkTimeoutSeconds: 5,
            // Sin red, la app sigue mostrando lo ultimo descargado durante el mes
            // que el pipeline conserva los dias. maxEntries cubre ~30 dias,
            // latest, index y los articulos abiertos; se expulsa el menos usado.
            expiration: { maxAgeSeconds: 30 * DIA, maxEntries: 150 },
          },
        }],
      },
    }),
  ],
})
