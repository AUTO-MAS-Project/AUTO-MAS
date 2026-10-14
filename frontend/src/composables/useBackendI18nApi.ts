import { Service } from '@/api'
import { requestApi } from '@/utils/apiResult'

/** 后端资源按当前界面语言读取，不改变语言配置的持久化归属。 */
export function useBackendI18nApi() {
  return {
    getLocales: () => requestApi(() => Service.getLocalesApiI18NLocalesGet(), '语言资源加载失败'),
    getMessages: (locale: string) =>
      requestApi(() => Service.getMessagesApiI18NMessagesGet(locale), '语言资源加载失败'),
  }
}
