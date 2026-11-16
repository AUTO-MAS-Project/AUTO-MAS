import { observePreference } from '@/utils/preferenceAnalytics'
//   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
//   Copyright © 2025-2026 AUTO-MAS Team

import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import 'dayjs/locale/en'
import 'dayjs/locale/ja'
import antdEnUS from 'ant-design-vue/es/locale/en_US'
import antdJaJP from 'ant-design-vue/es/locale/ja_JP'
import antdZhCN from 'ant-design-vue/es/locale/zh_CN'
import { message } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

import { i18n, normalizeLocale, t, type AppLocale } from '@/i18n'
import { getConfig, saveConfig, type FrontendConfig } from '@/utils/config'
import { useBackendI18nStore } from '@/stores/backendI18n'

const logger = window.electronAPI.getLogger('语言设置')

const DAYJS_LOCALE: Record<AppLocale, string> = {
  'zh-CN': 'zh-cn',
  'en-US': 'en',
  'ja-JP': 'ja',
}

const ANTD_LOCALE = {
  'zh-CN': antdZhCN,
  'en-US': antdEnUS,
  'ja-JP': antdJaJP,
}

// 模块级单例，与 useTheme 保持同一模式
const locale = ref<AppLocale>('zh-CN')
let initialized = false
let savedLocale: AppLocale = locale.value

/** 语言只影响展示层：vue-i18n 词表、dayjs 与 antd 组件内置文案。 */
function applyLocale(next: AppLocale): void {
  i18n.global.locale.value = next
  dayjs.locale(DAYJS_LOCALE[next])
}

watch(locale, applyLocale, { immediate: true })

/**
 * 首次启动跟随系统语言，之后以用户在设置里的选择为准。
 * 语言存在前端配置（Electron 侧）里，不经过后端。
 */
async function initLocale(preloadedConfig?: FrontendConfig): Promise<void> {
  if (initialized) return
  initialized = true
  try {
    const config = preloadedConfig ?? (await getConfig())
    if (config.language) {
      locale.value = normalizeLocale(config.language)
      return
    }
    // 未设置过则跟随系统：渲染进程的 navigator.language 即 Electron 的应用语言
    locale.value = normalizeLocale(navigator.language)
  } catch (error) {
    // 配置读不出来时仍能拿到系统语言，没必要连它一起放弃——
    // 「读取失败」和「语言标记不认识」是同一类情况，应给同一个答案。
    logger.warn(`读取语言设置失败，改用系统语言: ${error instanceof Error ? error.message : error}`)
    locale.value = normalizeLocale(navigator.language)
  } finally {
    savedLocale = locale.value
  }
}

// saveConfig 是「读全量 → 合并 → 写回」，并发调用会让先发的后完成从而覆盖后发的选择，
// 所以语言写入必须串行。
let savePending: Promise<void> = Promise.resolve()
let selectionId = 0
let appliedSelectionId = 0
const switching = ref(false)

async function setLocale(next: AppLocale): Promise<void> {
  // 不在此处按当前值早退：首启跟随系统时选择器已显示该语言，
  // 用户再显式选一次的意图是"钉住它"，必须落盘，否则日后仍会跟着系统变。
  const id = ++selectionId
  const resources = useBackendI18nStore()
  switching.value = true
  try {
    // 初始化期间所有词表都在本地；业务界面则须先准备目标语言及其回退资源。
    if (resources.ready && !(await resources.ensure(next))) {
      if (id === selectionId) message.error(t('bootstrap.i18n.unavailable'))
      return
    }
    if (id !== selectionId) return
    appliedSelectionId = id
    locale.value = next
    const previousSave = savePending
    savePending = observePreference('language', next, () =>
      previousSave
        .catch(() => {})
        .then(async () => {
          await saveConfig({ language: next })
          savedLocale = next
        })
    )
    await savePending
  } catch (error) {
    // 存不下就退回原值：否则界面显示的语言与重启后的语言不一致，且用户毫不知情。
    // 后一次资源请求失败并未切换界面；按最后实际应用的选择回退，避免遗留未保存语言。
    if (id === appliedSelectionId) locale.value = savedLocale
    logger.error(`保存语言设置失败: ${error instanceof Error ? error.message : error}`)
    message.error(t('bootstrap.common.languageSaveFailed'))
  } finally {
    if (id === selectionId) switching.value = false
  }
}

export function useLocale() {
  return {
    // 只读：改语言必须走 setLocale，否则会跳过持久化
    locale: computed(() => locale.value),
    antdLocale: computed(() => ANTD_LOCALE[locale.value]),
    switching: computed(() => switching.value),
    initLocale,
    setLocale,
  }
}
