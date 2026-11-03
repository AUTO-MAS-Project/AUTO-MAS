import type { ApplicationEnvironment } from '@/types/environment'

/** Electron 环境由主进程决定；纯浏览器预览才使用 Vite 的环境。 */
export const applicationEnvironment: ApplicationEnvironment =
  typeof window !== 'undefined' && window.appEnvironment
    ? window.appEnvironment
    : import.meta.env.DEV
      ? 'development'
      : 'production'

export const isDevelopmentEnvironment = applicationEnvironment === 'development'

/** 浏览器预览连接独立后端，不拥有其进程生命周期。 */
export function isBrowserDevelopment(): boolean {
  return (
    isDevelopmentEnvironment &&
    (window as Window & { __AUTO_MAS_BROWSER_DEV_MODE__?: boolean })
      .__AUTO_MAS_BROWSER_DEV_MODE__ === true
  )
}
