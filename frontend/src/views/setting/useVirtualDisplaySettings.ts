import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { ActionService, GetService, type GlobalConfig, type VirtualDisplayCheckOut } from '@/api'
import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'

export function useVirtualDisplaySettings(settings: () => GlobalConfig) {
  const { t } = useI18n()
  // 驱动状态在打开设置页时实时探测一次（只跑前两段，不动桌面拓扑，实测 0.2ms）。
  // 刻意不缓存也不持久化：存下来的状态只会变陈旧——驱动可能被卸载、被显卡驱动更新搞坏、
  // 或者配置被同步到另一台机器，而实时问一次永远是对的。
  const vddDriverReady = ref<boolean | null>(null)
  const vddDriverMessage = ref('')
  // 守卫此刻挂着的那块屏（设备名与模式），没挂时为 null。只是打开设置页时的一次快照，
  // 「立即拆除」按钮不按它禁用——守卫几秒一轮，快照很快就旧了，点了没挂后端会说没挂。
  const vddHolding = ref<string | null>(null)

  async function refreshVirtualDisplayStatus() {
    try {
      const res = await GetService.virtualDisplayStatusApiSettingVirtualDisplayStatusPost()
      vddDriverReady.value = (res.results ?? []).every(item => item.passed)
      vddDriverMessage.value = res.message ?? ''
      vddHolding.value = res.holding ?? null
    } catch {
      // 探测不出来就不拦——宁可让用户开着不生效，也不要因为一次查询失败把功能锁死。
      vddDriverReady.value = null
      vddDriverMessage.value = ''
      vddHolding.value = null
    }
  }

  onMounted(refreshVirtualDisplayStatus)

  // 驱动不可用时禁用开关，避免「开了但永远不生效」的假保障。
  // 但**已经开着**的时候必须留出关掉的余地，否则用户连关都关不掉。
  const vddSwitchDisabled = computed(
    () => vddDriverReady.value === false && !settings().Display?.IfEnableVirtualDisplay
  )

  const vddWarning = computed(() => {
    if (vddDriverReady.value !== false) return ''
    return settings().Display?.IfEnableVirtualDisplay
      ? t('setting.display.enabledButUnavailable', { reason: vddDriverMessage.value })
      : t('setting.display.driverUnavailable', { reason: vddDriverMessage.value })
  })

  const vddChecking = ref(false)
  const vddResult = ref<VirtualDisplayCheckOut | null>(null)
  // 结论这一行由前端出：后端文案是中文的，紧挨着英文标签太刺眼。明细仍用后端原文，
  // 那里带着版本号、实际模式、错误详情这些动态内容，与全站其它后端文案一致。
  const vddAllPassed = computed(() => (vddResult.value?.results ?? []).every(item => item.passed))

  async function runVirtualDisplayCheck() {
    vddChecking.value = true
    try {
      vddResult.value = await observeFeature(
        'virtual_display_action_finished',
        { action: 'check' },
        () => GetService.checkVirtualDisplayApiSettingVirtualDisplayCheckPost(),
        result =>
          result.code !== 200
            ? apiOutcome(result)
            : !result.results?.length
              ? 'unknown'
              : result.results.every(item => item.passed)
                ? 'success'
                : 'failure'
      )
      await refreshVirtualDisplayStatus()
    } catch {
      vddResult.value = null
      message.error(t('setting.display.checkFailed'))
    } finally {
      vddChecking.value = false
    }
  }

  // 手动拆除：真实显示器回来时的询问弹窗之外的兜底入口——弹窗被关掉、或者用户想在任务
  // 结束前把屏拆掉，都从这里走。任务在不在跑都照拆，那是用户的决定。
  const vddDetaching = ref(false)

  async function runVirtualDisplayDetach() {
    vddDetaching.value = true
    try {
      const res = await observeFeature(
        'virtual_display_action_finished',
        { action: 'remove' },
        () => ActionService.detachVirtualDisplayApiSettingVirtualDisplayDetachPost(),
        result =>
          result.code !== 200 ? apiOutcome(result) : result.detached ? 'success' : 'skipped'
      )
      if (res.code !== 200) {
        message.error(`${t('setting.display.detachFailed')}: ${res.message}`)
        return
      }
      if (res.detached) {
        message.success(t('setting.display.detachDone'))
      } else {
        message.info(t('setting.display.detachNothing'))
      }
      await refreshVirtualDisplayStatus()
    } catch {
      message.error(t('setting.display.detachFailed'))
    } finally {
      vddDetaching.value = false
    }
  }

  return {
    vddDriverReady,
    vddDriverMessage,
    vddHolding,
    vddSwitchDisabled,
    vddWarning,
    vddChecking,
    vddResult,
    vddAllPassed,
    runVirtualDisplayCheck,
    vddDetaching,
    runVirtualDisplayDetach,
  }
}
