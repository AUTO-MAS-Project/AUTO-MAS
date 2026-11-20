import { computed, inject, provide, ref, watch, type InjectionKey, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useActiveTriggers } from '@/composables/useActiveTriggers'
import { usePluginApi } from '@/composables/usePluginApi'
import { apiErrorMessage } from '@/utils/apiResult'
import {
  actionEditable,
  type InstalledFilter,
  type InstalledPluginView,
  type LifecycleAction,
  type MarketFilter,
} from './pluginCenterModel'
import {
  createPluginOperationLock,
  type PluginOperationAction,
  type PluginOperationLock,
} from './pluginOperationLock'
import { usePluginCenterData, type PluginCenterData } from './usePluginCenterData'
import { usePluginInstallation, type PluginInstallationController } from './usePluginInstallation'

export type PluginCenterTab = 'installed' | 'market' | 'updates'

export interface PluginCenterContext {
  data: PluginCenterData
  installation: PluginInstallationController
  lock: PluginOperationLock
  /** 外壳工具条的搜索与筛选，按页签分开保存。 */
  installedQuery: Ref<string>
  installedFilter: Ref<InstalledFilter>
  marketQuery: Ref<string>
  marketFilter: Ref<MarketFilter>
  /**
   * 提交启用、停用、重载或卸载命令：占用全局插件操作锁，按界面提示判断可否执行，
   * 完成后提示并回读列表与用量。确认与拦截弹层由调用方先处理（见 lifecycleDecision）。
   */
  runLifecycle(view: InstalledPluginView, action: LifecycleAction): Promise<boolean>
}

const pluginActions = new Set<string>(['install', 'enable', 'disable', 'reload', 'uninstall'])
const isPluginAction = (field: string): field is PluginOperationAction => pluginActions.has(field)

const PLUGIN_CENTER_KEY: InjectionKey<PluginCenterContext> = Symbol('plugin-center')

/** 外壳调用一次：建立取数、安装状态与操作锁，并向三个页签提供。 */
export function providePluginCenter(): PluginCenterContext {
  const { t } = useI18n()
  const api = usePluginApi()
  const data = usePluginCenterData()
  const { data: activeTriggers } = useActiveTriggers()
  const activePluginTriggers = computed(() =>
    activeTriggers.value.flatMap(trigger =>
      trigger.group === 'info' && isPluginAction(trigger.field)
        ? [{ uid: trigger.configUid, action: trigger.field, taskId: trigger.taskId }]
        : []
    )
  )
  const lock = createPluginOperationLock(() => activePluginTriggers.value[0] ?? null)
  watch(activePluginTriggers, (next, previous) => {
    if (previous.some(trigger => !next.some(current => current.taskId === trigger.taskId)))
      void data.reload()
  })
  const installation = usePluginInstallation(lock, {
    onInstalled: data.reload,
    activeInstalls: () =>
      activePluginTriggers.value.flatMap(trigger =>
        trigger.action === 'install' ? [trigger.uid] : []
      ),
    latest: uid => data.market.value.find(entry => entry.uid === uid)?.document,
  })

  const runLifecycle = async (view: InstalledPluginView, action: LifecycleAction) => {
    if (!actionEditable(view, action) || !lock.acquire({ uid: view.uid, action })) return false
    try {
      const result = await api.runCommand(action, {
        configUid: view.uid,
        group: 'info',
        field: action,
        value: true,
      })
      message.success(result.message || t('core.plugins.actionComplete'))
      await data.reload()
      return true
    } catch (error) {
      message.error(apiErrorMessage(error, t('core.plugins.actionFailed')))
      return false
    } finally {
      lock.release()
    }
  }

  const context: PluginCenterContext = {
    data,
    installation,
    lock,
    installedQuery: ref(''),
    installedFilter: ref<InstalledFilter>('all'),
    marketQuery: ref(''),
    marketFilter: ref<MarketFilter>('all'),
    runLifecycle,
  }
  provide(PLUGIN_CENTER_KEY, context)
  return context
}

/** 三个页签与它们的子组件取插件中心上下文；必须在外壳之内使用。 */
export function usePluginCenter(): PluginCenterContext {
  const context = inject(PLUGIN_CENTER_KEY, null)
  if (!context) throw new Error('usePluginCenter() 只能在插件中心外壳内使用')
  return context
}
