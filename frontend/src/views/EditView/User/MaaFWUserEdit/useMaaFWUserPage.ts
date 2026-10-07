import {
  computed,
  markRaw,
  nextTick,
  onBeforeUnmount,
  onMounted,
  onUnmounted,
  ref,
  shallowRef,
} from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { buildMaaFWAssetUrl, useMaaFWApi } from '@/composables/useMaaFWApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import {
  isMaaFWFamily,
  maafwUserConfigTypes,
  prepareMaaFWFlavorPage,
  useMaaFWFlavor,
  type MaaFWUserSlotContext,
} from '@/composables/useMaaFWFlavor'
import type {
  MaaFWInterfacePreviewData,
  MaaFWScriptConfig,
  MaaFWTaskSnapshot,
  MaaFWUserConfig,
  ScriptType,
} from '@/types/script'
import { managedMaaFWQueueState } from '../maafwManagedTasks'
import { normalizeTaskSnapshot } from './maafwTaskSnapshot'
import { useMaaFWUserSaveStatus } from './useMaaFWUserSaveStatus'
import { useMaaFWUserForm } from './useMaaFWUserForm'
import { useMaaFWUserTaskContext } from './useMaaFWUserTaskContext'
import { useMaaFWUserPersistence, type MaaFWUserIdHolder } from './useMaaFWUserPersistence'
import { useMaaFWTaskQueue } from './useMaaFWTaskQueue'
import { useMaaFWAddTaskMenu } from './useMaaFWAddTaskMenu'
import { useMaaFWUserQueueImport } from './useMaaFWUserQueueImport'
import { useMaaFWQueueTemplates } from './useMaaFWQueueTemplates'
import { useMaaFWUserConfigRestore } from './useMaaFWUserConfigRestore'
import { maafwRouteLocation } from '@/router/maafwFlavorRoutes'
import { useMaaFWPageHostContext } from '../../MaaFWFlavor/pageHostContext'

export interface MaaFWUserPageOptions {
  scriptId: string
  /** 编辑模式下的用户 id；新建模式为空，加载时现建一个 */
  userId: string
}

/**
 * MFW 用户页的编排层：脚本身份与 flavor、加载（脚本 → interface → 用户 / 新建用户）、
 * 特调提示与插入点上下文、离开确认与生命周期，返回模板要用的全部状态与动作。
 *
 * `isInitializing` 只在用户数据回填完成（或加载用户出错）时放开，此前两条落盘路径都不写。
 */
export function useMaaFWUserPage({ scriptId, userId }: MaaFWUserPageOptions) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('MaaFW用户编辑')
  const router = useRouter()
  const { addUser, getUsers } = useUserApi()
  const { getScript } = useScriptApi()
  const { loading: interfaceLoading, previewInterface } = useMaaFWApi()

  const pageLoading = ref(true)
  const loading = computed(() => pageLoading.value)
  const isInitializing = ref(true)
  const { isSaving, hasUnsavedChanges, saveStatus, saveErrorMessage, enqueueSave, pendingCount } =
    useMaaFWUserSaveStatus()

  const userIdHolder: MaaFWUserIdHolder = { value: userId }
  const isEdit = ref(!!userIdHolder.value)
  const { configLocked } = useScriptConfigLock(() => scriptId)

  const scriptName = ref('')
  const scriptPath = ref('')
  // flavor 文案以脚本当前类型为准（MaaFW / M9A / MSS ……），不看路由 meta。
  // 在页面宿主里时类型是宿主的那一份：写回去宿主才知道要不要换页面。
  const host = useMaaFWPageHostContext()
  const scriptType = host?.scriptType ?? ref<ScriptType>('MaaFW')
  const flavor = useMaaFWFlavor(scriptType)
  /** 面包屑回脚本页：按脚本当前类型走它那条线 */
  const scriptRoute = computed(() =>
    maafwRouteLocation(scriptType.value, 'script', { id: scriptId })
  )
  const scriptConfig = ref<MaaFWScriptConfig | null>(null)
  const preferAdbController = ref(false)
  const previewData = shallowRef<MaaFWInterfacePreviewData | null>(null)

  const projectIconUrl = computed(() =>
    buildMaaFWAssetUrl(previewData.value?.path, previewData.value?.project.icon)
  )

  const handleProjectIconError = (event: Event) => {
    const image = event.currentTarget as HTMLImageElement | null
    if (!image || image.dataset.maafwIconFallbackApplied === 'true') return
    image.dataset.maafwIconFallbackApplied = 'true'
    image.src = flavor.value.logo
  }
  const taskSnapshot = ref<MaaFWTaskSnapshot>({
    taskOrder: [],
    taskChecked: {},
    taskOptions: {},
  })

  const { formData, rules, applyUserData } = useMaaFWUserForm()

  /** 队列提示按条目给出（文案里用 \n 分行），渲染成列表而不是一坨文字 */
  const queueHintLines = computed(() =>
    t(flavor.value.userPage.text.queueHintKey ?? '')
      .split('\n')
      .map(line => line.trim())
      .filter(Boolean)
  )

  const accountRecordTooltip = computed(() => t(flavor.value.userPage.text.accountTooltipKey))

  const context = useMaaFWUserTaskContext({
    previewData,
    scriptConfig,
    preferAdbController,
    interfaceLoading,
    flavor,
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
  const { presentQueuedTasks, syncControllerResourceSelection } = queue

  const menu = useMaaFWAddTaskMenu({ scriptId, previewData, taskSnapshot, context, queue })

  const userImport = useMaaFWUserQueueImport({ scriptId, userIdHolder, queue })
  const templates = useMaaFWQueueTemplates({ scriptId, scriptConfig, taskSnapshot, queue })

  // 队列里残留的受管任务：只有真要拆用户（后端会拒绝运行）才给警告，其余是运行照常的轻提示
  const managedQueueAlert = computed<{ type: 'warning' | 'info'; message: string } | null>(() => {
    const state = managedMaaFWQueueState(presentQueuedTasks.value, {
      managedEntries: managedTaskEntries.value,
      accountTask: flavor.value.userPage.managed.accountTask,
      resourceName: effectiveResourceName.value,
      taskOptions: taskSnapshot.value.taskOptions,
      options: previewData.value?.options || [],
      displayName: task => getDisplayName(task),
    })
    if (state?.kind === 'split' && flavor.value.userPage.managed.warningKey) {
      return { type: 'warning', message: t(flavor.value.userPage.managed.warningKey, state) }
    }
    if (state?.kind === 'notice' && flavor.value.userPage.managed.noticeKey) {
      return { type: 'info', message: t(flavor.value.userPage.managed.noticeKey, state) }
    }
    return null
  })

  // 特调插入点的上下文：独有区块直接改 formData 草稿，落盘走 save 事件回到 handleFieldSave
  const flavorSlotContext = computed<MaaFWUserSlotContext>(() => ({
    formData,
    loading: loading.value,
    // 虚影不会运行，不算进队列（MSS 靠它提示「队列为空又没选计划表」）
    queuedTaskCount: presentQueuedTasks.value.length,
    previewData: previewData.value,
    scriptId,
  }))

  const loadScriptInfo = async () => {
    pageLoading.value = true
    try {
      // 页面宿主已经读过脚本详情就直接用（null 是读过但没读到），不再请求一次
      const initialScript = host?.takeInitialScript()
      const script = initialScript !== undefined ? initialScript : await getScript(scriptId)
      if (!script) {
        message.error(t('edit.scriptDoesNotExist2'))
        handleCancel()
        return
      }
      // MaaFW 与它的特调类型（M9A / MSS ……）都是同一个页面
      if (!isMaaFWFamily(script.type)) {
        message.error(t('edit.scriptTypeNotMfw'))
        handleCancel()
        return
      }

      scriptType.value = script.type
      scriptName.value = script.name
      const loadedScriptConfig = script.config as MaaFWScriptConfig
      scriptConfig.value = loadedScriptConfig
      scriptPath.value = loadedScriptConfig.Info?.Path || ''
      preferAdbController.value = Boolean(
        loadedScriptConfig.Emulator?.Id && loadedScriptConfig.Emulator.Id !== '-'
      )
      // 特调独有区块的数据与组件和 interface 一起备好，卡片出来时已经齐了
      await Promise.all([reloadInterface(false), prepareMaaFWFlavorPage(flavor.value, 'userPage')])

      if (isEdit.value) {
        await loadUserData()
      } else {
        await createUserImmediately()
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载脚本信息失败: ${errorMsg}`)
      message.error(t('edit.couldNotLoadScript2'))
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
        message.error(t('edit.couldNotCreateUser'))
        handleCancel()
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`创建用户失败: ${errorMsg}`)
      message.error(t('edit.couldNotCreateUser'))
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

        // 特调的用户类是 MaaFWUserConfig 的子类（如 MSS 多一项 Info.PlanMode），同一个页面
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
          await syncControllerResourceSelection()
          formData.Task.TaskSnapshot = JSON.stringify(taskSnapshot.value)
          await nextTick()
          formData.userName = formData.Info.Name || ''
          hasUnsavedChanges.value = false
          isInitializing.value = false
        } else {
          message.error(t('edit.userDoesNotExist'))
          handleCancel()
        }
      } else {
        message.error(t('edit.couldNotFetchUser'))
        handleCancel()
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载用户数据失败: ${errorMsg}`)
      message.error(t('edit.couldNotLoadUser2'))
      isInitializing.value = false
      handleCancel()
    }
  }

  const reloadInterface = async (showMessage = true) => {
    if (!scriptPath.value) {
      if (showMessage) message.warning(t('edit.importMfwProjectScript'))
      return
    }

    previewData.value = null
    const data = await previewInterface(scriptPath.value, scriptId)
    if (data) {
      previewData.value = markRaw(data)
      taskSnapshot.value = normalizeTaskSnapshot(taskSnapshot.value, data, { keepMissing: true })
      await syncControllerResourceSelection()
      await nextTick()
      if (showMessage) message.success(t('edit.interfaceLoaded'))
    }
  }

  const handleCancel = () => {
    if (isSaving.value || hasUnsavedChanges.value) {
      Modal.confirm({
        title: t('edit.youHaveUnsavedChanges'),
        content: t('edit.leaveWithoutSavingUnsaved'),
        okText: t('edit.leave'),
        cancelText: t('edit.keepEditing'),
        onOk: () => router.push('/scripts'),
      })
      return
    }
    router.push('/scripts')
  }

  const handleBeforeUnload = (event: BeforeUnloadEvent) => {
    if (!isSaving.value && !hasUnsavedChanges.value) return
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
      message.error(t('edit.missingScriptIdParameter'))
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
    flavor,
    scriptRoute,
    previewData,
    interfaceLoading,
    projectIconUrl,
    handleProjectIconError,
    taskSnapshot,
    formData,
    rules,
    queueHintLines,
    accountRecordTooltip,
    managedQueueAlert,
    flavorSlotContext,
    taskByName: context.taskByName,
    effectiveControllerName: context.effectiveControllerName,
    effectiveResourceName,
    interfaceDependentDisabled: context.interfaceDependentDisabled,
    handleFieldSave,
    ...queue,
    ...menu,
    ...userImport,
    ...templates,
    ...restore,
    loadUserData,
    reloadInterface,
    handleCancel,
  }
}
