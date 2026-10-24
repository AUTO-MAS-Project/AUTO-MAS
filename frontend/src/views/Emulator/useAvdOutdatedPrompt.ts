import { Modal } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'

import { useAvdUpdateApi } from '@/composables/useAvdUpdateApi'
import { versionLabel } from './avdLogic'

/**
 * 魔改 AVD 开不了机、而且是版本低于 MAS 的最低要求（开机前检查拒绝）时，直接给出「去更新」。
 *
 * 只认「这个根目录能更新、版本低于最低要求」这一种情况；别的开机失败照旧只由系统通知说明原因。
 * ``openRoot``：用户点「去更新」后打开这个根目录的「管理与更新」弹窗。
 */
export function useAvdOutdatedPrompt(openRoot: (root: string) => void) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('Emulator2')
  const updateApi = useAvdUpdateApi()

  const offerAvdUpdate = async (root: string) => {
    try {
      const status = await updateApi.getStatus(root)
      if (!status.updatable || !status.belowMinimum) return
      Modal.confirm({
        title: t('emulator2.avd.update.outdatedTitle'),
        content: t('emulator2.avd.update.outdatedContent', {
          current: versionLabel(status.currentBuild, status.currentVersion),
          minimum: status.minimumBuild,
        }),
        okText: t('emulator2.avd.update.goUpdate'),
        cancelText: t('emulator.cancel'),
        onOk: () => openRoot(root),
      })
    } catch (error) {
      logger.warn(`读取魔改 AVD 更新状态失败 (${root}): ${String(error)}`)
    }
  }

  return { offerAvdUpdate }
}
