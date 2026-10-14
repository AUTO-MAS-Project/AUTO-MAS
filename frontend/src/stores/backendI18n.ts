import { defineStore } from 'pinia'
import { ref, watch, type WatchStopHandle } from 'vue'
import { i18n, type AppLocale } from '@/i18n'
import zhCN from '@/i18n/locales/zh-CN'
import enUS from '@/i18n/locales/en-US'
import jaJP from '@/i18n/locales/ja-JP'
import { useBackendI18nApi } from '@/composables/useBackendI18nApi'
import { connectionState } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import { apiErrorMessage } from '@/utils/apiResult'

const localMessages = { 'zh-CN': zhCN, 'en-US': enUS, 'ja-JP': jaJP }
const resourceLocale: Record<AppLocale, string> = { 'zh-CN': 'zh_CN', 'en-US': 'en', 'ja-JP': 'ja' }

type Messages = { [key: string]: string | Messages }

/** 资源只接受文本和嵌套词表，阻止特殊对象键进入 Vue I18n。 */
function messageTree(value: unknown, prefix = ''): Messages {
  const result: Messages = {}
  if (!value || typeof value !== 'object' || Array.isArray(value)) return result
  for (const [key, item] of Object.entries(value)) {
    if (['__proto__', 'prototype', 'constructor'].includes(key)) continue
    // 后端无译文时返回完整 key；不让这种占位覆盖既有界面词表。
    if (typeof item === 'string' && item !== `${prefix}${key}`) result[key] = item
    else if (item && typeof item === 'object' && !Array.isArray(item))
      result[key] = messageTree(item, `${prefix}${key}.`)
  }
  return result
}

export const useBackendI18nStore = defineStore('backend-i18n', () => {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const revision = ref('')
  const pluginNames = ref<string[]>([])
  const api = useBackendI18nApi()
  let requestId = 0
  let stopWatch: WatchStopHandle | null = null
  let subscription: string | null = null

  async function refresh() {
    const id = ++requestId
    const locale = i18n.global.locale.value
    loading.value = true
    error.value = null
    try {
      const state = await api.getLocales()
      const requested = resourceLocale[locale]
      const selected = state.data.available.includes(requested) ? requested : state.data.fallback
      const response = await api.getMessages(selected)
      if (id !== requestId) return
      const messages = messageTree(response.data.messages)
      const base = messageTree(localMessages[locale])
      // 替换后端命名空间，已卸载插件的旧词条不会残留；保留原页面词表。
      i18n.global.setLocaleMessage<Messages>(locale, {
        ...base,
        ...messages,
        plugins: {
          ...(typeof base.plugins === 'object' ? base.plugins : {}),
          ...(typeof messages.plugins === 'object' ? messages.plugins : {}),
        },
      })
      pluginNames.value = Object.keys(typeof messages.plugins === 'object' ? messages.plugins : {})
      revision.value = response.data.revision
    } catch (reason) {
      if (id === requestId) error.value = apiErrorMessage(reason, '语言资源加载失败')
    } finally {
      if (id === requestId) loading.value = false
    }
  }

  function bootstrap() {
    if (stopWatch) return
    subscription = subscribe({ id: 'I18n', type: 'i18n.updated' }, () => void refresh())
    stopWatch = watch(
      [connectionState(), i18n.global.locale],
      ([state]) => {
        if (state === 'open') void refresh()
      },
      { immediate: true }
    )
  }

  function dispose() {
    stopWatch?.()
    stopWatch = null
    if (subscription) unsubscribe(subscription)
    subscription = null
    requestId++
    loading.value = false
  }

  return { loading, error, revision, pluginNames, refresh, bootstrap, dispose }
})

export const bootstrapBackendI18n = () => useBackendI18nStore().bootstrap()
export const disposeBackendI18n = () => useBackendI18nStore().dispose()
