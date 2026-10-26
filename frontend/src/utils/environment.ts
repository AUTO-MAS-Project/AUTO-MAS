import type { ApplicationEnvironment } from '@/types/environment'

/** Electron 环境由主进程决定；纯浏览器预览才使用 Vite 的环境。 */
export const applicationEnvironment: ApplicationEnvironment =
  typeof window !== 'undefined' && window.appEnvironment
    ? window.appEnvironment
    : import.meta.env.DEV
      ? 'development'
      : 'production'

export const isDevelopmentEnvironment = applicationEnvironment === 'development'
