import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The built assets are served by the Python service under /ui/app/.
// Relative base keeps the asset URLs valid under that path.
export default defineConfig({
  base: './',
  plugins: [vue()],
  build: {
    outDir: '../src/webui/dist',
    emptyOutDir: true,
  },
})
