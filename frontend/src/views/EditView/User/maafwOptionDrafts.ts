// MFW 选项编辑器里还没提交的草稿（文本 / 数字 / 密码字段失焦或回车才提交）。
// 页面离开（点「返回」、关窗口）前要先把它们提交掉，提交不了（校验不过）的按未保存处理；
// 编辑器在页面上可能有好几个（全局选项、任务选项、各层子选项），由页面提供一个登记处统一调度。

import type { InjectionKey } from 'vue'
import type { MaaFWTaskOptionValue } from '@/types/script'
import { storedMaaFWInputFieldValue } from './maafwOptionValues'

export interface MaaFWOptionDraftHolder {
  /** 有没有和已存值不同、还没提交的草稿 */
  hasPending: () => boolean
  /** 提交全部草稿；还有校验不过、留在框里的返回 false */
  flush: () => boolean
}

export interface MaaFWOptionDraftRegistry {
  /** 登记一个编辑器，返回注销函数 */
  register: (holder: MaaFWOptionDraftHolder) => () => void
  hasPending: () => boolean
  flush: () => boolean
}

export const MAAFW_OPTION_DRAFTS_KEY: InjectionKey<MaaFWOptionDraftRegistry> =
  Symbol('maafwOptionDrafts')

export const createMaaFWOptionDraftRegistry = (): MaaFWOptionDraftRegistry => {
  const holders = new Set<MaaFWOptionDraftHolder>()
  return {
    register: holder => {
      holders.add(holder)
      return () => {
        holders.delete(holder)
      }
    },
    hasPending: () => [...holders].some(holder => holder.hasPending()),
    flush: () => {
      let allCommitted = true
      for (const holder of [...holders]) {
        if (!holder.flush()) allCommitted = false
      }
      return allCommitted
    },
  }
}

/** 草稿键：`选项名\u0000字段名` */
export const maafwOptionDraftKey = (optionName: string, inputName: string) =>
  `${optionName}\u0000${inputName}`

export const parseMaaFWOptionDraftKey = (key: string) => {
  const index = key.indexOf('\u0000')
  return { optionName: key.slice(0, index), inputName: key.slice(index + 1) }
}

/**
 * 选项值换了一份（保存后按后端结果重载、配置恢复、换了任务）时，只丢掉那些字段的已存值
 * 确实变了的草稿；字段没变的草稿留着，用户正在输入的内容不被别处的重载冲掉。
 */
export const retainMaaFWDraftsForUnchangedFields = (
  drafts: Record<string, string>,
  previous: Record<string, MaaFWTaskOptionValue> | undefined,
  next: Record<string, MaaFWTaskOptionValue> | undefined
): Record<string, string> =>
  Object.fromEntries(
    Object.entries(drafts).filter(([key]) => {
      const { optionName, inputName } = parseMaaFWOptionDraftKey(key)
      return (
        storedMaaFWInputFieldValue(previous?.[optionName], inputName) ===
        storedMaaFWInputFieldValue(next?.[optionName], inputName)
      )
    })
  )
