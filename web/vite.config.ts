import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  // 加载环境变量
  const env = loadEnv(mode, '.', '')
  
  return {
    plugins: [vue()],
    server: {
      host: env.VITE_DEV_HOST || '127.0.0.1',
      port: parseInt(env.VITE_DEV_PORT || '5173'),
    },
  }
})
