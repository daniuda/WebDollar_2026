import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: process.env.NODE_ENV === 'production' ? '/tracker/' : '/',
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
