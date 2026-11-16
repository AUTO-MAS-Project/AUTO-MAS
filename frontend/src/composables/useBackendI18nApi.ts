import { Service } from '@/api'
import { t, type AppLocale } from '@/i18n'
import { getApiErrorMessage } from '@/utils/apiError'

/** 只通过生成客户端读取资源；语言偏好由 Electron 保存。 */
export function useBackendI18nApi() {
  async function getLocales() {
    try {
      const response = await Service.getLocalesApiI18NLocalesGet()
      if (response.code !== 200) throw new Error(response.message)
      return response.data
    } catch (error) {
      throw new Error(getApiErrorMessage(error, t('bootstrap.i18n.unavailable')))
    }
  }

  async function getMessages(locale: AppLocale) {
    try {
      const response = await Service.getMessagesApiI18NMessagesGet(locale)
      if (response.code !== 200) throw new Error(response.message)
      return response.data
    } catch (error) {
      throw new Error(getApiErrorMessage(error, t('bootstrap.i18n.unavailable')))
    }
  }

  return { getLocales, getMessages }
}
