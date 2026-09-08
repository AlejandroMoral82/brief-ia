import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  base: '/brief-ia/',
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Brief IA',
        short_name: 'Brief',
        start_url: '/brief-ia/',
        display: 'standalone',
        background_color: '#070908',
        theme_color: '#070908',
      },
      workbox: {
        runtimeCaching: [{
          urlPattern: /\/data\/.*\.json$/,
          handler: 'NetworkFirst',
          options: { cacheName: 'brief-data' },
        }],
      },
    }),
  ],
})