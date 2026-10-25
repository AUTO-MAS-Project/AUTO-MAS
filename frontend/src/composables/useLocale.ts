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

import { ensureLocaleMessages, i18n, normalizeLocale, t, type AppLocale } from '@/i18n'
import { getConfig, saveConfig, type FrontendConfig } from '@/utils/config'

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

// 连点语言选择时，先发的请求可能后完成（切日文要拉词表，切中文立刻返回），
// 按完成顺序定胜负会让旧选择盖掉用户最后一次点击。每次切换领一个序号，
// 只有序号仍是最新的请求能改界面语言、能落盘。
let localeRequestSeq = 0

/** 语言只影响展示层：vue-i18n 词表、dayjs 与 antd 组件内置文案。 */
function applyLocale(next: AppLocale): void {
  i18n.global.locale.value = next
  dayjs.locale(DAYJS_LOCALE[next])
}

/**
 * 切到某语言前先备好它的词表。
 *
 * 词表是按语言的独立分块，locale 先改而词表没到，界面会先渲染出一批裸 key。
 * 加载失败时保留当前语言，并把失败原因交给调用方决定要不要提示。
 */
async function prepareLocale(next: AppLocale): Promise<boolean> {
  try {
    await ensureLocaleMessages(next)
    return true
  } catch (error) {
    logger.error(`加载语言词表失败: ${error instanceof Error ? error.message : error}`)
    return false
  }
}

watch(locale, applyLocale, { immediate: true })

/**
 * 首次启动跟随系统语言，之后以用户在设置里的选择为准。
 * 语言存在前端配置（Electron 侧）里，不经过后端。
 */
async function initLocale(preloadedConfig?: FrontendConfig): Promise<void> {
  if (initialized) return
  initialized = true
  // 首启的语言也算一次请求：用户在词表加载期间手动选了语言，别让首启结果反盖回去
  const requestId = ++localeRequestSeq
  try {
    const config = preloadedConfig ?? (await getConfig())
    // 未设置过则跟随系统：渲染进程的 navigator.language 即 Electron 的应用语言
    const next = config.language
      ? normalizeLocale(config.language)
      : normalizeLocale(navigator.language)
    // 拉不到就先停在源语言上，总比界面上全是裸 key 好
    if (!(await prepareLocale(next))) return
    if (requestId !== localeRequestSeq) return
    locale.value = next
  } catch (error) {
    // 配置读不出来时仍能拿到系统语言，没必要连它一起放弃——
    // 「读取失败」和「语言标记不认识」是同一类情况，应给同一个答案。
    logger.warn(`读取语言设置失败，改用系统语言: ${error instanceof Error ? error.message : error}`)
    if (requestId === localeRequestSeq) locale.value = normalizeLocale(navigator.language)
  }
}

// saveConfig 是「读全量 → 合并 → 写回」，并发调用会让先发的后完成从而覆盖后发的选择，
// 所以语言写入必须串行。
let savePending: Promise<void> = Promise.resolve()

async function setLocale(next: AppLocale): Promise<void> {
  // 不在此处按当前值早退：首启跟随系统时选择器已显示该语言，
  // 用户再显式选一次的意图是"钉住它"，必须落盘，否则日后仍会跟着系统变。
  const previous = locale.value
  const requestId = ++localeRequestSeq
  // 词表没到就切 locale，界面会先闪一帧裸 key，所以失败时不切
  if (!(await prepareLocale(next))) {
    // 已经切到别的语言就不再报错，否则连点会连弹几条
    if (requestId === localeRequestSeq) message.error(t('common.languageLoadFailed'))
    return
  }
  // 等词表期间用户又选了别的语言：这次请求作废，不能让旧选择盖掉新选择
  if (requestId !== localeRequestSeq) return
  locale.value = next

  savePending = savePending.catch(() => {}).then(() => saveConfig({ language: next }))
  try {
    await savePending
  } catch (error) {
    // 存不下就退回原值：否则界面显示的语言与重启后的语言不一致，且用户毫不知情。
    // 只在自己仍是最新选择时回退，避免踩掉后一次切换。
    if (locale.value === next) locale.value = previous
    logger.error(`保存语言设置失败: ${error instanceof Error ? error.message : error}`)
    message.error(t('common.languageSaveFailed'))
  }
}

export function useLocale() {
  return {
    // 只读：改语言必须走 setLocale，否则会跳过持久化
    locale: computed(() => locale.value),
    antdLocale: computed(() => ANTD_LOCALE[locale.value]),
    initLocale,
    setLocale,
  }
}
