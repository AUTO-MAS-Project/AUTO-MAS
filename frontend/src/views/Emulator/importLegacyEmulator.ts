import type { EmulatorSearchResult } from '@/api'
import { Service } from '@/api'
import { beginAnalyticsOperation } from '@/utils/analytics'

/** 创建空记录与写配置是一个导入流程；已创建但未配置单独记为部分完成。 */
export async function importLegacyEmulator(result: EmulatorSearchResult, onCreated: () => void) {
  const telemetry = beginAnalyticsOperation('emulator_discovery_finished')
  const emulator_family =
    result.type === 'mumu'
      ? ('mumu' as const)
      : result.type === 'ldplayer'
        ? ('leidian' as const)
        : ('unknown' as const)
  const props = { action: 'import' as const, emulator_family, count_bucket: '1' as const }
  let added = false
  try {
    const created = await Service.addEmulatorApiEmulatorAddPost()
    if (created.code !== 200) {
      telemetry.finish({ ...props, outcome: 'failure' })
      return created
    }
    added = true
    onCreated()
    const response = await Service.updateEmulatorApiEmulatorUpdatePost({
      emulatorId: created.emulatorId,
      data: {
        Info: {
          Name: result.name,
          Type: result.type as 'general' | 'mumu' | 'ldplayer',
          Path: result.path,
          MaxWaitTime: 300,
          BossKey: JSON.stringify([]),
        },
      },
    })
    telemetry.finish({ ...props, outcome: response.code === 200 ? 'success' : 'partial' })
    return response
  } catch (error) {
    telemetry.finish({ ...props, outcome: added ? 'partial' : 'unknown' })
    throw error
  }
}
