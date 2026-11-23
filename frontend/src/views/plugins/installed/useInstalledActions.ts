import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { openConfirm } from '@/composables/useConfirm'
import {
  LIFECYCLE_LABEL_KEYS,
  lifecycleDecision,
  type DisableScope,
  type InstalledPluginView,
  type LifecycleAction,
  type LifecycleDecision,
} from '../pluginCenterModel'
import { usePluginCenter } from '../usePluginCenter'

export type GuardedAction = 'disable' | 'uninstall'

interface LifecycleGuard {
  uid: string
  action: GuardedAction
}

const CONFIRM_TITLE_KEYS: Record<GuardedAction, string> = {
  disable: 'core.plugins.disableConfirmTitle',
  uninstall: 'core.plugins.uninstallConfirmTitle',
}

const isBlocked = (decision: LifecycleDecision) =>
  decision.kind === 'blockedInUse' || decision.kind === 'blockedUnknown'

/**
 * 已安装页签的操作编排：启用、重载直接提交；停用、卸载先按 lifecycleDecision 拦截或确认。
 * 能对上托管类型的插件在判断前先重取一次用量。
 * 拦截弹层打开期间，用量重新读到后若已不再拦截，就关掉弹层接着走确认或直接执行。
 */
export function useInstalledActions() {
  const { t } = useI18n()
  const { data, installation, lock, runLifecycle } = usePluginCenter()
  const guard = ref<LifecycleGuard | null>(null)

  const guardView = computed(
    () => (guard.value && data.installed.value.find(view => view.uid === guard.value?.uid)) || null
  )
  const guardDecision = computed<LifecycleDecision | null>(() =>
    guard.value && guardView.value
      ? lifecycleDecision(guard.value.action, guardView.value, data.usageOf(guardView.value))
      : null
  )

  const confirm = (view: InstalledPluginView, action: GuardedAction, scopes: DisableScope[]) =>
    // 沿用原有确认文案：卸载始终提示删除配置，停用列出后端给的影响范围。
    openConfirm({
      tone: 'danger',
      title: t(CONFIRM_TITLE_KEYS[action]),
      description:
        action === 'uninstall'
          ? t('core.plugins.uninstallConfirmContent', { name: view.name })
          : t('core.plugins.disableConfirmContent', {
              name: view.name,
              scopes: scopes.map(scope => t(`core.plugins.disableScope.${scope}`)).join(' / '),
            }),
      okText: t(LIFECYCLE_LABEL_KEYS[action]),
      cancelText: t('core.common.cancel'),
    })

  const proceed = async (
    view: InstalledPluginView,
    action: GuardedAction,
    decision: LifecycleDecision
  ): Promise<boolean> => {
    if (isBlocked(decision)) {
      guard.value = { uid: view.uid, action }
      return false
    }
    if (decision.kind === 'confirm' && !(await confirm(view, action, decision.scopes))) return false
    return runLifecycle(view, action)
  }

  const request = async (view: InstalledPluginView, action: LifecycleAction): Promise<boolean> => {
    if (action === 'enable' || action === 'reload') return runLifecycle(view, action)
    let target = view
    if (view.binding) {
      // 用量是进页时取的快照，托管可能已在别处新建：判断前重取一次。
      // 重取期间占用全局锁（该行显示进行中、按钮置灰，不能重复点）；失败时按「读取失败」分支拦住。
      if (!lock.acquire({ uid: view.uid, action })) return false
      try {
        await data.reloadUsage()
      } finally {
        lock.release()
      }
      const latest = data.installed.value.find(item => item.uid === view.uid)
      if (!latest) return false
      target = latest
    }
    return proceed(target, action, lifecycleDecision(action, target, data.usageOf(target)))
  }

  const upgrade = (view: InstalledPluginView): Promise<boolean> =>
    view.upgrade ? installation.install(view.upgrade.document) : Promise.resolve(false)

  watch(guardDecision, decision => {
    const current = guard.value
    if (!current) return
    const view = guardView.value
    if (!view || !decision) {
      // 插件已不在列表里（例如被别处卸载），弹层没有对象可说。
      guard.value = null
      return
    }
    if (isBlocked(decision)) return
    guard.value = null
    void proceed(view, current.action, decision)
  })

  return {
    guardAction: computed(() => guard.value?.action ?? null),
    guardView,
    guardDecision,
    closeGuard: () => (guard.value = null),
    retryUsage: () => data.reloadUsage(),
    request,
    upgrade,
  }
}
