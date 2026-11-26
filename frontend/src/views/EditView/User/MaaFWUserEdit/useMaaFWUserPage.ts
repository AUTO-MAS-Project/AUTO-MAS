import { useGamesApi } from '@/composables/useGamesApi'
import {
  computed,
  getCurrentInstance,
  markRaw,
  nextTick,
  onBeforeUnmount,
  onMounted,
  onUnmounted,
  provide,
  ref,
  shallowRef,
} from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { openConfirm } from '@/composables/useConfirm'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { useMaaFWApi } from '@/composables/useMaaFWApi'
import { buildMaaFWScriptIconUrl } from '@/utils/maafwProjectIcon'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import {
  isMaaFWFamily,
  maafwLogo,
  maafwUserConfigTypes,
  maafwUsesProjectIcon,
  type MaaFWFamilyType,
} from '@/plugins/maafwFamily'
import type {
  MaaFWInterfacePreviewData,
  MaaFWScriptConfig,
  MaaFWTaskSnapshot,
  MaaFWUserConfig,
  ScriptType,
} from '@/types/script'
import { managedMaaFWQueueState, type MaaFWManagedAccountTask } from '../maafwManagedTasks'
import { unselectableMaaFWQueueNotices } from '../maafwUnselectableTasks'
import { createMaaFWOptionDraftRegistry, MAAFW_OPTION_DRAFTS_KEY } from '../maafwOptionDrafts'
import { normalizeTaskSnapshot } from './maafwTaskSnapshot'
import { useMaaFWUserSaveStatus } from './useMaaFWUserSaveStatus'
import { createMaaFWLeaveGuard } from './maafwLeaveGuard'
import { useMaaFWUserForm } from './useMaaFWUserForm'
import { useMaaFWUserTaskContext } from './useMaaFWUserTaskContext'
import { useMaaFWUserPersistence, type MaaFWUserIdHolder } from './useMaaFWUserPersistence'
import { useMaaFWTaskQueue } from './useMaaFWTaskQueue'
import { useMaaFWAddTaskMenu } from './useMaaFWAddTaskMenu'
import { useMaaFWUserQueueImport } from './useMaaFWUserQueueImport'
import { useMaaFWQueueTemplates } from './useMaaFWQueueTemplates'
import { useMaaFWUserConfigRestore } from './useMaaFWUserConfigRestore'
import { maafwRouteLocation } from '@/router/maafwRoutes'
import { useMaaFWPageHostContext } from '../../MaaFW/pageHostContext'

/** 受管任务：由后端专项全权控制的任务（M9A 的启动游戏、切换账号、关闭游戏） */
export interface MaaFWManagedTasks {
  /**
   * 不许用户自己加的任务（interface 里任务的 entry）：用户页「添加任务」与预设模板里都不出现。
   * 已经在队列里的照常显示（能看能删），并按 warningKey 在队列上方给一条警告
   */
  entries: readonly string[]
  /**
   * 受管的切号任务：资源在 resources 里、队列里它的有效实例（目标账号非空）≥ 2 时，后端拒绝
   * 运行该用户、要求拆成多个用户（与后端同一判据）。没有写 null
   */
  accountTask: MaaFWManagedAccountTask | null
  /** 需要拆用户时的警告（插值 count：个数，accounts：各目标账号）；为空则不显示 */
  warningKey: string | null
  /** 其余受管任务残留在队列里时的提示（插值 tasks：任务名；运行照常）；为空则不显示 */
  noticeKey: string | null
}

const NO_MANAGED_TASKS: MaaFWManagedTasks = {
  entries: [],
  accountTask: null,
  warningKey: null,
  noticeKey: null,
}

export interface MaaFWUserPageOptions {
  scriptId: string
  /** 编辑模式下的用户 id；新建模式为空，加载时现建一个 */
  userId: string
  /** 页面自己的类型（MaaFW / M9A / MSS）：头像用项目图标还是类型图标按它取 */
  type: MaaFWFamilyType
  /** 受管任务；不写就是没有 */
  managed?: MaaFWManagedTasks
  /** 任务队列区顶部的提示（t() 用的 key，\n 分行，一行一个框）；不写不显示 */
  queueHintKey?: string
  /** 页面加载期间（与读取 interface 并行）调用，给页面独有区块备数据；失败自行兜底，不要抛 */
  prepare?: () => Promise<void>
}

/**
 * MFW 用户页的编排层：脚本身份、加载（脚本 → interface → 用户 / 新建用户）、受管任务与队列提示、
 * 离开确认与生命周期，返回模板要用的全部状态与动作。
 *
 * `isInitializing` 只在用户数据回填完成（或加载用户出错）时放开，此前两条落盘路径都不写。
 */
export function useMaaFWUserPage({
  scriptId,
  userId,
  type,
  managed = NO_MANAGED_TASKS,
  queueHintKey,
  prepare,
}: MaaFWUserPageOptions) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('MaaFW用户编辑')
  const router = useRouter()
  const { addUser, getUsers, error: userApiError } = useUserApi()
  const { getScript, error: scriptApiError } = useScriptApi()
  const { loading: interfaceLoading, previewInterface } = useMaaFWApi()

  const pageLoading = ref(true)
  const loading = computed(() => pageLoading.value)
  const isInitializing = ref(true)
  /** 用户数据回填成功，页面真正能用了（与 isInitializing 不同，加载出错离页时保持 false） */
  const userLoaded = ref(false)
  const {
    isSaving,
    hasUnsavedChanges,
    saveStatus,
    saveErrorMessage,
    enqueueSave,
    waitForSaves,
    resetSaveFailures,
    pendingCount,
  } = useMaaFWUserSaveStatus()

  // 页面上各个选项编辑器里没提交的草稿（文本 / 数字 / 密码失焦才提交），离开页面前统一提交
  const optionDrafts = createMaaFWOptionDraftRegistry()
  if (getCurrentInstance()) provide(MAAFW_OPTION_DRAFTS_KEY, optionDrafts)

  const userIdHolder: MaaFWUserIdHolder = { value: userId }
  const isEdit = ref(!!userIdHolder.value)
  const { configLocked } = useScriptConfigLock(() => scriptId)

  const scriptName = ref('')
  const scriptPath = ref('')
  // 脚本类型（MaaFW / M9A / MSS），不看路由 meta：在页面宿主里时以宿主读到的为初值，
  // 读到脚本详情后以它为准。
  const host = useMaaFWPageHostContext()
  const scriptType = ref<ScriptType>(host?.scriptType.value ?? 'MaaFW')
  /** 面包屑回脚本页：按脚本当前类型走它那条线 */
  const scriptRoute = computed(() =>
    maafwRouteLocation(scriptType.value, 'script', { id: scriptId })
  )
  const scriptConfig = ref<MaaFWScriptConfig | null>(null)
  const games = useGamesApi()
  const preferAdbController = computed(
    () =>
      games.rows.value.find(game => game.uid === scriptConfig.value?.game.game_id)?.type.kind ===
      'emulator'
  )
  const previewData = shallowRef<MaaFWInterfacePreviewData | null>(null)

  // M9A、MSS 用自己的图标（模板里回退到类型图标）；通用 MFW 与脚本列表同一个口径取项目图标，
  // 不等 interface 读完
  const projectIconUrl = computed(() =>
    maafwUsesProjectIcon(type) ? buildMaaFWScriptIconUrl(scriptId) : ''
  )

  const handleProjectIconError = (event: Event) => {
    const image = event.currentTarget as HTMLImageElement | null
    if (!image || image.dataset.maafwIconFallbackApplied === 'true') return
    image.dataset.maafwIconFallbackApplied = 'true'
    image.src = maafwLogo(type)
  }
  const taskSnapshot = ref<MaaFWTaskSnapshot>({
    taskOrder: [],
    taskChecked: {},
    taskOptions: {},
  })

  const { formData, rules, applyUserData } = useMaaFWUserForm()

  /** 队列提示按条目给出（文案里用 \n 分行），渲染成列表而不是一坨文字 */
  const pageQueueHintLines = computed(() =>
    t(queueHintKey ?? '')
      .split('\n')
      .map(line => line.trim())
      .filter(Boolean)
  )

  const context = useMaaFWUserTaskContext({
    previewData,
    scriptConfig,
    preferAdbController,
    interfaceLoading,
    managedEntries: managed.entries,
  })
  const { effectiveResourceName, managedTaskEntries, isManagedTaskId, getDisplayName } = context

  const { handleFieldSave, savePresetAndSnapshot } = useMaaFWUserPersistence({
    scriptId,
    userIdHolder,
    formData,
    taskSnapshot,
    previewData,
    isInitializing,
    isManagedTaskId,
    enqueueSave,
    pendingCount,
  })

  const queue = useMaaFWTaskQueue({
    previewData,
    taskSnapshot,
    formData,
    context,
    savePresetAndSnapshot,
  })
  const { presentQueuedTasks } = queue

  const menu = useMaaFWAddTaskMenu({
    scriptId,
    previewData,
    taskSnapshot,
    context,
    queue,
    ready: userLoaded,
  })

  const userImport = useMaaFWUserQueueImport({ scriptId, userIdHolder, queue })
  const templates = useMaaFWQueueTemplates({ scriptId, scriptConfig, taskSnapshot, queue })

  // 队列里残留的受管任务：只有真要拆用户（后端会拒绝运行）才给警告，其余是运行照常的轻提示
  const managedQueueAlert = computed<{ type: 'warning' | 'info'; message: string } | null>(() => {
    const state = managedMaaFWQueueState(presentQueuedTasks.value, {
      managedEntries: managedTaskEntries.value,
      // MAS 原生登录（Run.LoginMode = Mas）时切号由 MAS 完成，队列里的切号是残留、后端会直接移出，
      // 不会拒跑，也就不给「拆分前不会运行」的警告
      accountTask: scriptConfig.value?.Run?.LoginMode === 'Mas' ? null : managed.accountTask,
      resourceName: effectiveResourceName.value,
      taskOptions: taskSnapshot.value.taskOptions,
      options: previewData.value?.options || [],
      displayName: task => getDisplayName(task),
      separator: t('core.edit.maafwUnselectableTaskSeparator'),
    })
    if (state?.kind === 'split' && managed.warningKey) {
      return { type: 'warning', message: t(managed.warningKey, state) }
    }
    if (state?.kind === 'notice' && managed.noticeKey) {
      return { type: 'info', message: t(managed.noticeKey, state) }
    }
    return null
  })

  // 队列里的不可选任务（后端专项声明，如 M9A 的小游戏）照常显示：同一原因并成一句「运行时会跳过」，
  // 接在页面的队列提示后面，一句一个框
  const queueHintLines = computed(() => [
    ...pageQueueHintLines.value,
    ...unselectableMaaFWQueueNotices(
      presentQueuedTasks.value,
      task => getDisplayName(task),
      t('core.edit.maafwUnselectableTaskSeparator')
    ).map(notice => t('core.edit.maafwUnselectableTaskNotice', notice)),
  ])

  // 任务队列里的任务实例数：虚影不会运行，不算进队列（MSS 靠它提示「队列为空又没选计划表」）
  const queuedTaskCount = computed(() => presentQueuedTasks.value.length)

  /**
   * 「配置导入」把外壳里的队列写进了用户：把实际落盘的快照规整成用户页自己的形状换进本地状态就行——
   * 写库那次请求后端已经做完了，这里再来一次 persistQueuedSnapshot 就是同一个动作写两遍。
   * 特调整理时一并改掉的账号 / 备注（M9A 把切换账号收进账号）也同步过来，否则页面上还是旧值。
   */
  const handleShellImported = (
    snapshot: Record<string, unknown>,
    info: Record<string, unknown>
  ) => {
    taskSnapshot.value = normalizeTaskSnapshot(snapshot, previewData.value, {
      keepMissing: true,
    })
    // 队列被换掉了，原来选的预设不再对得上（后端那次写入也清了它）
    formData.Task.SelectedPreset = ''
    if (typeof info.Id === 'string') formData.Info.Id = info.Id
    if (typeof info.Notes === 'string') formData.Info.Notes = info.Notes
  }

  // 页面的 prepare：失败只影响独有区块自己，不拖垮页面加载，也从不往外抛（同步抛出的也收住）
  const runPrepare = async () => {
    if (!prepare) return
    await Promise.allSettled([(async () => prepare())()])
  }

  const loadScriptInfo = async () => {
    pageLoading.value = true
    try {
      // 页面宿主已经读过脚本详情就直接用（null 是读过但没读到），不再请求一次
      const initialScript = host?.takeInitialScript()
      const script = initialScript !== undefined ? initialScript : await getScript(scriptId)
      if (!script) {
        if (!scriptApiError.value && !host?.scriptLoadError.value)
          message.error(t('core.edit.scriptDoesNotExist2'))
        handleCancel()
        return
      }
      // 只有 MaaFW 家族（MaaFW / M9A / MSS）的脚本由 MFW 用户页编辑
      if (!isMaaFWFamily(script.type)) {
        message.error(t('core.edit.scriptTypeNotMfw'))
        handleCancel()
        return
      }

      scriptType.value = script.type
      scriptName.value = script.name
      const loadedScriptConfig = script.config as MaaFWScriptConfig
      scriptConfig.value = loadedScriptConfig
      scriptPath.value = loadedScriptConfig.Info?.Path || ''
      // 页面独有区块的数据和 interface 一起备好，卡片出来时已经齐了
      await Promise.all([reloadInterface(false), runPrepare()])

      if (isEdit.value) {
        await loadUserData()
      } else {
        await createUserImmediately()
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载脚本信息失败: ${errorMsg}`)
      if (!scriptApiError.value) message.error(t('core.edit.couldNotLoadScript2'))
      handleCancel()
    } finally {
      pageLoading.value = false
    }
  }

  const createUserImmediately = async () => {
    if (configLocked.value) return false

    try {
      const result = await addUser(scriptId)
      if (result?.userId) {
        userIdHolder.value = result.userId
        isEdit.value = true
        // 去脚本实际类型那条线的编辑用户路由，别把 M9A 落到 MFW 的 URL 上
        router.replace(
          maafwRouteLocation(scriptType.value, 'userEdit', { scriptId, userId: result.userId })
        )
        await loadUserData()
      } else {
        if (!userApiError.value) message.error(t('core.edit.couldNotCreateUser'))
        handleCancel()
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`创建用户失败: ${errorMsg}`)
      if (!userApiError.value) message.error(t('core.edit.couldNotCreateUser'))
      handleCancel()
    }
  }

  const loadUserData = async () => {
    try {
      const userResponse = await getUsers(scriptId, userIdHolder.value)

      if (userResponse?.code === 200) {
        const userIndex = userResponse.index.find(index => index.uid === userIdHolder.value)
        const userData = userResponse.data[userIdHolder.value] as
          | Partial<MaaFWUserConfig>
          | undefined

        // M9A、MSS 的用户类是 MaaFWUserConfig 的子类（如 MSS 多一项 Info.PlanMode）
        const isMaaFWUser = Boolean(userIndex && maafwUserConfigTypes().has(userIndex.type))
        if (isMaaFWUser && userData) {
          applyUserData(userData)
          taskSnapshot.value = normalizeTaskSnapshot(
            formData.Task.TaskSnapshot,
            previewData.value,
            {
              keepMissing: true,
            }
          )
          formData.Task.TaskSnapshot = JSON.stringify(taskSnapshot.value)
          await nextTick()
          formData.userName = formData.Info.Name || ''
          // 页面上的值换成了后端这一份：之前没存上的改动已不在，失败账一并清掉
          resetSaveFailures()
          isInitializing.value = false
          userLoaded.value = true
        } else {
          message.error(t('core.edit.userDoesNotExist'))
          handleCancel()
        }
      } else {
        if (!userApiError.value) message.error(t('core.edit.couldNotFetchUser'))
        handleCancel()
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载用户数据失败: ${errorMsg}`)
      if (!userApiError.value) message.error(t('core.edit.couldNotLoadUser2'))
      isInitializing.value = false
      handleCancel()
    }
  }

  const reloadInterface = async (showMessage = true) => {
    if (!scriptPath.value) {
      if (showMessage) message.warning(t('core.edit.importMfwProjectScript'))
      return
    }

    previewData.value = null
    const data = await previewInterface(scriptPath.value, scriptId)
    if (data) {
      previewData.value = markRaw(data)
      taskSnapshot.value = normalizeTaskSnapshot(taskSnapshot.value, data, { keepMissing: true })
      await nextTick()
      if (showMessage) message.success(t('core.edit.interfaceLoaded'))
    }
  }

  // 离开本页（「返回」、面包屑、侧栏、浏览器后退……）都走同一个路由离开守卫：
  // 先提交选项编辑器里没提交的草稿；还在保存（改完输入框直接点走，失焦刚触发了保存）就先等它
  // 存完；只有存失败、或有校验不过的草稿时才弹确认，选「继续编辑」就留在本页。
  // 转圈、连点只算一次、放行后不再拦见 createMaaFWLeaveGuard。
  const confirmLeave = () =>
    openConfirm({
      tone: 'warning',
      title: t('core.edit.youHaveUnsavedChanges'),
      description: t('core.edit.leaveWithoutSavingUnsaved'),
      okText: t('core.edit.leave'),
      cancelText: t('core.edit.keepEditing'),
    })

  const prepareLeave = async () => {
    const draftsCommitted = optionDrafts.flush()
    if (isSaving.value) await waitForSaves()
    if (draftsCommitted && !hasUnsavedChanges.value) return true
    return await confirmLeave()
  }

  const {
    leaving,
    guard: guardLeave,
    reset: resetLeaveApproval,
  } = createMaaFWLeaveGuard(prepareLeave)

  // 守卫只能在组件 setup 里挂（单测在 effectScope 里跑这个组合式函数，没有组件实例）
  if (getCurrentInstance()) {
    onBeforeRouteLeave(() => guardLeave())
    // 放行后这次导航没走成（被别的守卫拦下，或中途抛错）、页面还在：下次离开照常检查
    onUnmounted(router.afterEach(() => resetLeaveApproval()))
    onUnmounted(router.onError(() => resetLeaveApproval()))
  }

  // 「返回」只负责发起导航，检查都在离开守卫里
  const handleCancel = () => {
    if (leaving.value) return
    void router.push('/scripts')
  }

  // 关窗口 / 刷新：同步提交草稿（提交会立刻排进保存队列，isSaving 随之为真），
  // 提交不了的草稿与还在保存、保存失败一样拦下来
  const handleBeforeUnload = (event: BeforeUnloadEvent) => {
    const draftsCommitted = optionDrafts.flush()
    if (draftsCommitted && !isSaving.value && !hasUnsavedChanges.value) return
    event.preventDefault()
    event.returnValue = ''
  }

  const restore = useMaaFWUserConfigRestore({
    scriptId,
    userIdHolder,
    loadUserData,
    reloadInterface,
  })
  const { ensureMaaFWBackup } = restore

  onMounted(() => {
    window.addEventListener('beforeunload', handleBeforeUnload)
    if (!scriptId) {
      message.error(t('core.edit.missingScriptIdParameter'))
      handleCancel()
      return
    }

    // 先等脚本信息与用户就绪（新建模式内部会创建用户并写入 userId）再归档，
    // 否则新建用户首次进入会因 userId 未就绪静默跳过归档
    void (async () => {
      await loadScriptInfo()
      void ensureMaaFWBackup('native')
    })()
  })

  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', handleBeforeUnload)
  })

  onUnmounted(() => {
    // 退出编辑页：归档 MAS 用户字段侧车终态（编辑会话包络；MaaFW 无遮罩会话）
    void ensureMaaFWBackup('mas')
  })

  return {
    loading,
    saveStatus,
    saveErrorMessage,
    userIdHolder,
    isEdit,
    configLocked,
    scriptName,
    scriptType,
    scriptRoute,
    previewData,
    interfaceLoading,
    projectIconUrl,
    handleProjectIconError,
    taskSnapshot,
    formData,
    rules,
    queueHintLines,
    managedQueueAlert,
    queuedTaskCount,
    handleShellImported,
    taskByName: context.taskByName,
    effectiveControllerName: context.effectiveControllerName,
    effectiveResourceName,
    managedTaskEntries,
    interfaceDependentDisabled: context.interfaceDependentDisabled,
    handleFieldSave,
    ...queue,
    ...menu,
    ...userImport,
    ...templates,
    ...restore,
    loadUserData,
    reloadInterface,
    leaving,
    handleCancel,
  }
}
