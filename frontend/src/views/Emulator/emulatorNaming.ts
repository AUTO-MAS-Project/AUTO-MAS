import { Service } from '@/api'
import { translate as t } from '@/i18n'
import { invalidateEmulatorOptions } from '@/composables/useEmulatorOptions'

/**
 * 新建模拟器后按界面语言写默认名，并让模拟器下拉缓存失效。
 *
 * 后端 app/models/config/emulator.py 的 default_factory 是中文「新模拟器」，
 * 英文/日文界面下新标签直接显示中文；这里按界面语言改名并避开已有名字，
 * 用户才看得懂这个标签是谁。改名是新增模拟器流程的一部分，随后必须刷新
 * 下拉选项缓存，否则选择器里看不到新条目。
 */
export const nameNewEmulator = async (
  emulatorId: string,
  index: ReadonlyArray<{ uid: string }>,
  data: Record<string, { Info?: { Name?: string } } | undefined>
): Promise<void> => {
  const base = t('emulator.defaultName')
  const existing = new Set(index.map(item => String(data[item.uid]?.Info?.Name ?? '')))
  let name = base
  if (existing.has(name)) {
    for (let suffix = 2; suffix < 1000; suffix += 1) {
      const candidate = `${base} ${suffix}`
      if (!existing.has(candidate)) {
        name = candidate
        break
      }
    }
  }
  await Service.updateEmulatorApiEmulatorUpdatePost({
    emulatorId,
    data: { Info: { Name: name } },
  })
  await invalidateEmulatorOptions()
}
