<template>
  <WhimboxUserEditHeader
    :script-id="scriptId"
    :script-name="scriptName"
    :is-edit="isEdit"
    @restore="openRestoreModal"
    @back="handleCancel"
  />

  <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
    <a-card class="config-card">
      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <BasicInfoSection
          :form-data="formData"
          :loading="loading"
          @save="handleFieldSave"
          @mode-change="handleConfigModeChange"
        />

        <TaskConfigSection
          :loading="loading"
          :steps="catalogSteps"
          :options="catalogOptions"
          :upstream-version="catalogData?.upstream_version ?? ''"
          :catalog-error="catalogError"
          :catalog-loading="catalogLoading || isInitializing"
          :run-all-accounts="formData.OneDragon.IfRunAllAccounts"
          :tasks="taskState"
          :option-state="optionState"
          @save="handleTaskConfigSave"
          @tasks-change="handleTasksChange"
          @options-change="handleOptionsChange"
        />

        <ExtraScriptSection :form-data="formData" :loading="loading" @save="handleFieldSave" />

        <UserNotifyConfig v-model="formData.Notify" :loading="loading" @save="handleFieldSave" />
      </a-form>
    </a-card>
  </ConfigLockPanel>

  <!-- ══ 配置恢复（通用组件：MAS 用户字段 + 奇想盒原生配置双池）══ -->
  <ConfigRestoreSection
    v-model:open="restoreOpen"
    :disabled="configLocked"
    :script-name="WHIMBOX_DISPLAY_NAME"
    :targets="restoreTargets"
    :api="restoreApi"
    :user-desc="t('edit.whimboxConfigRestoreUserDesc')"
    :script-desc="t('edit.whimboxConfigRestoreScriptDesc')"
    :on-restored="handleRestored"
  >
    <!-- 两池同构：预览载荷为分区行（文件清单由基座在预览区最下方统一渲染） -->
    <template #preview="{ raw }">
      <a-empty
        v-if="!previewSections(raw).length"
        :description="t('edit.configRestorePreviewEmpty')"
      />
      <template v-else>
        <template v-for="section in previewSections(raw)" :key="section.name">
          <h4 class="whimbox-preview-section">{{ section.label }}</h4>
          <a-descriptions :column="1" size="small" bordered class="whimbox-preview-box">
            <a-descriptions-item v-for="row in section.rows" :key="row.key" :label="row.key">
              {{ row.value }}
            </a-descriptions-item>
          </a-descriptions>
        </template>
      </template>
    </template>
  </ConfigRestoreSection>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { useSaveQueue } from '@/composables/useSaveQueue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { useWhimboxTaskCatalog } from '@/composables/useWhimboxTaskCatalog'
import { Service } from '@/api'
import type { WhimboxOptionCatalogItem, WhimboxTaskCatalogItem } from '@/api'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import BasicInfoSection from '@/views/WhimboxUserEdit/BasicInfoSection.vue'
import TaskConfigSection from '@/views/WhimboxUserEdit/TaskConfigSection.vue'
import WhimboxUserEditHeader from '@/views/WhimboxUserEdit/WhimboxUserEditHeader.vue'
import { WHIMBOX_CONFIG_MODES } from '@/views/WhimboxUserEdit/modes'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('奇想盒用户编辑')

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers } = useUserApi()
const { getScript } = useScriptApi()
const {
  loading: catalogLoading,
  error: catalogError,
  data: catalogData,
  fetchCatalog,
} = useWhimboxTaskCatalog()

const formRef = ref<FormInstance>()
const isInitializing = ref(true) // 标记是否正在初始化
// 保存请求不再驱动整页 loading，避免每次自动保存都让表单快速闪动（对齐 MaaEndUserEdit）
const loading = computed(() => isInitializing.value)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { enqueue } = useSaveQueue()

// 路由参数
const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId) // 使用 ref 以便在创建后更新
// 任务运行期锁定配置编辑（保存门禁在 useUserApi 内，这里只做界面提示与禁用）
const { configLocked } = useScriptConfigLock(() => scriptId)

// 脚本信息
const scriptName = ref('')

// 奇想盒专项统一名（文案参数化用）
const WHIMBOX_DISPLAY_NAME = '奇想盒'

// ══ 任务目录（字段定义与值域全部来自后端下发，前端零硬编码步骤键）══
const catalogSteps = computed<WhimboxTaskCatalogItem[]>(() => catalogData.value?.steps ?? [])
const catalogOptions = computed<WhimboxOptionCatalogItem[]>(() => catalogData.value?.options ?? [])

// 步骤开关覆盖集与目标/参数覆盖集（运行时序列化为 JSON map 存 Task.Tasks/Task.Options）
const taskState = reactive<Record<string, boolean>>({})
const optionState = reactive<Record<string, unknown>>({})

// 奇想盒用户默认数据（与后端 WhimboxUserConfig 的默认值保持一致）
const getDefaultWhimboxUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    Mode: '脚本',
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
    Tag: '',
  },
  OneDragon: {
    IfRunAllAccounts: false,
  },
  Task: {
    Tasks: '{ }',
    Options: '{ }',
  },
  Data: {
    LastProxyDate: '2000-01-01',
    ProxyTimes: 0,
    LastProxyStatus: '未知',
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
  },
})

// 创建扁平化的表单数据，用于表单验证
const formData = reactive({
  // 扁平化的验证字段
  userName: '',
  // 嵌套的实际数据
  ...getDefaultWhimboxUserData(),
})

// 表单验证规则
const rules = computed(() => {
  const baseRules: Record<string, Rule[]> = {
    userName: [
      { required: true, message: t('edit.enterUsername'), trigger: 'blur' },
      { min: 1, max: 50, message: t('edit.usernameMustBe1'), trigger: 'blur' },
    ],
  }
  return baseRules
})

// 同步扁平化字段与嵌套数据
watch(
  () => formData.Info.Name,
  newVal => {
    if (formData.userName !== newVal) {
      formData.userName = newVal || ''
    }
  },
  { immediate: true }
)

watch(
  () => formData.userName,
  newVal => {
    if (formData.Info.Name !== newVal) {
      formData.Info.Name = newVal || ''
    }
  }
)

// 配置来源切换：校验 value ∈ 两态白名单 → 赋值 Info.Mode → 保存
const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string') return
  if (!(WHIMBOX_CONFIG_MODES as readonly string[]).includes(value)) return
  formData.Info.Mode = value
  await handleFieldSave('Info.Mode', formData.Info.Mode)
}

// 把覆盖集 JSON（字符串或已解对象）安全解为 dict
const parseOverrideMap = (raw: unknown): Record<string, unknown> => {
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as Record<string, unknown>
  }
  if (typeof raw === 'string' && raw.trim()) {
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>
      }
    } catch {
      // 损坏的存量数据按空集处理
    }
  }
  return {}
}

// 覆盖集写回：子组件上抛整张 map，这里序列化保存（单键粒度无意义，map 即最小语义单元）
const handleTasksChange = async (tasks: Record<string, boolean>) => {
  Object.keys(taskState).forEach(key => delete taskState[key])
  Object.assign(taskState, tasks)
  await handleFieldSave('Task.Tasks', JSON.stringify(tasks))
}

const handleOptionsChange = async (options: Record<string, unknown>) => {
  Object.keys(optionState).forEach(key => delete optionState[key])
  Object.assign(optionState, options)
  await handleFieldSave('Task.Options', JSON.stringify(options))
}

// 任务配置区的静态字段保存：先同步本地表单值（开关受控于 formData），再落库
const handleTaskConfigSave = async (key: string, value: unknown) => {
  if (key === 'OneDragon.IfRunAllAccounts') {
    formData.OneDragon.IfRunAllAccounts = value === true
  }
  await handleFieldSave(key, value)
}

// 即时保存单个字段变更（局部更新，不整体覆盖用户配置）
// 入队而非互斥：同一字段的连续改动只保留最后一次，前一次在途也不会丢弃后一次
const handleFieldSave = async (key: string, value: any) => {
  if (isInitializing.value || !userId) return

  // 解析 key 路径，例如 "Info.Status" -> { Info: { Status: value } }
  const parts = key.split('.')
  let userData: Record<string, any> = {}
  let current = userData

  for (let i = 0; i < parts.length - 1; i++) {
    current[parts[i]] = {}
    current = current[parts[i]]
  }
  current[parts[parts.length - 1]] = value

  // 特殊处理：userName 需要同步到 Info.Name
  if (key === 'userName') {
    userData = { Info: { Name: value } }
  }

  await enqueue(async () => {
    try {
      await updateUser(scriptId, userId, userData)
      logger.info(`用户配置已保存: ${key}`)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存失败: ${errorMsg}`)
    }
  }, key)
}

// ══ 配置恢复（通用组件 props 供给：MAS 用户字段 + 奇想盒原生配置双池）══
const restoreOpen = ref(false)

// 目标池顺序 = segmented 展示顺序：MAS 用户字段（在前）、奇想盒原生配置（在后）
const restoreTargets: Array<{ key: string; kind: 'user' | 'script' }> = [
  { key: 'mas', kind: 'user' },
  { key: 'native', kind: 'script' },
]

const restoreApi = {
  list: async (target: string) =>
    Service.listConfigBackupsApiApiScriptsBackupListGet(scriptId, userId, target),
  preview: async (target: string, time: string) =>
    Service.getConfigBackupPreviewApiApiScriptsBackupPreviewGet(scriptId, userId, time, target),
  restore: async (target: string, time: string) =>
    Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
      scriptId,
      userId,
      time,
      target,
    }),
  readFile: async (target: string, time: string, path: string) =>
    Service.getConfigBackupFileApiApiScriptsBackupFileGet(scriptId, userId, time, target, path),
}

const openRestoreModal = () => {
  restoreOpen.value = true
}

// 预览响应原文收敛为分区视图（两池同构：sections[].rows[]；文件清单由基座渲染）
interface WhimboxPreviewSection {
  name: string
  label: string
  rows: Array<{ key: string; value: string }>
}
const previewSections = (raw: unknown): WhimboxPreviewSection[] => {
  if (!raw || typeof raw !== 'object') return []
  const sections = (raw as { sections?: unknown }).sections
  if (!Array.isArray(sections)) return []
  return sections
    .filter((s): s is Record<string, unknown> => Boolean(s && typeof s === 'object'))
    .map(s => ({
      name: String(s.name ?? ''),
      label: String(s.label ?? ''),
      rows: Array.isArray(s.rows)
        ? s.rows
            .filter((r): r is Record<string, unknown> => Boolean(r && typeof r === 'object'))
            .map(r => ({ key: String(r.key ?? ''), value: String(r.value ?? '') }))
        : [],
    }))
    .filter(s => s.rows.length > 0)
}

const handleRestored = async (target: string) => {
  restoreOpen.value = false
  // 成功提示由基座组件给出（ConfigRestoreSection），此处只负责表单刷新
  if (target !== 'mas') return
  // mas 恢复 = 字段回填：重拉表单，否则旧表单值下次保存会静默覆盖恢复结果
  isInitializing.value = true
  try {
    await loadUserData()
  } finally {
    isInitializing.value = false
  }
}

// 编辑界面归档（进入归档原生配置、退出归档 MAS 字段终态；指纹去重）
// 归档失败不能静默：源配置损坏时该端点返回 code=400 + 带损坏位置的原文文案
// （后端明确要求前端透传），吞掉会让用户以为已留下恢复点
const ensureBackup = async (target: 'mas' | 'native') => {
  if (!userId) return
  try {
    const resp = await Service.ensureConfigBackupApiApiScriptsBackupEnsurePost({
      scriptId,
      userId,
      target,
    })
    if (resp.code !== 200) {
      const detail = resp.message || t('edit.configRestoreEnsureFailed')
      logger.warn(`编辑页归档失败（不阻断编辑）: ${detail}`)
      message.warning(detail)
    }
  } catch (error) {
    // 传输层失败没有可透传的业务文案，退回通用提示
    logger.warn(`编辑页归档失败（不阻断编辑）: ${String(error)}`)
    message.warning(t('edit.configRestoreEnsureFailed'))
  }
}

// 加载脚本信息
const loadScriptInfo = async () => {
  try {
    const script = await getScript(scriptId)
    if (script) {
      scriptName.value = script.name
      if (script.type !== 'Whimbox') {
        message.error(t('edit.whimboxNotWhimboxScript'))
        handleCancel()
        return
      }

      // 任务目录与脚本信息并行拉取；目录失败只降级该区块，不阻断编辑
      void fetchCatalog(scriptId)

      // 如果是编辑模式，加载用户数据
      if (isEdit.value) {
        await loadUserData()
      } else {
        // 新增模式：立即创建用户获取 ID
        await createUserImmediately()
      }
    } else {
      message.error(t('edit.scriptDoesNotExist2'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
    message.error(t('edit.couldNotLoadScript2'))
  }
}

// 新增模式下立即创建用户
const createUserImmediately = async () => {
  try {
    const result = await addUser(scriptId)
    if (result && result.userId) {
      userId = result.userId
      isEdit.value = true
      // 切到 edit 路由：add 路由不含 :userId 段，停留在 add 路由会丢掉参数、刷新即重复建用户
      await router.replace({
        name: 'WhimboxUserEdit',
        params: { scriptId, userId },
      })
      logger.info(`用户已创建，ID: ${result.userId}`)
      // 加载新创建用户的数据
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

// 加载用户数据
const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)

    if (userResponse && userResponse.code === 200) {
      // 查找指定的用户数据
      const userIndex = userResponse.index.find(index => index.uid === userId)
      if (userIndex && userResponse.data[userId]) {
        const userData = userResponse.data[userId] as any

        // 填充奇想盒用户数据
        if (userIndex.type === 'WhimboxUserConfig') {
          Object.assign(formData, {
            Info: { ...getDefaultWhimboxUserData().Info, ...userData.Info },
            OneDragon: {
              ...getDefaultWhimboxUserData().OneDragon,
              ...userData.OneDragon,
            },
            Task: { ...getDefaultWhimboxUserData().Task, ...userData.Task },
            Notify: { ...getDefaultWhimboxUserData().Notify, ...userData.Notify },
            Data: { ...getDefaultWhimboxUserData().Data, ...userData.Data },
          })

          // 覆盖集 JSON → 可编辑状态
          Object.keys(taskState).forEach(k => delete taskState[k])
          const tasks = parseOverrideMap(userData.Task?.Tasks)
          for (const [k, v] of Object.entries(tasks)) {
            taskState[k] = Boolean(v)
          }
          Object.keys(optionState).forEach(k => delete optionState[k])
          Object.assign(optionState, parseOverrideMap(userData.Task?.Options))
        }

        // 同步扁平化字段 - 使用nextTick确保数据更新完成后再同步
        await nextTick()
        formData.userName = formData.Info.Name || ''

        logger.info('用户数据加载成功')

        void ensureBackup('native')

        // 数据加载完成，允许自动保存
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
    // 复位初始化标志：否则 loading 恒真、整页控件永久禁用（只能刷新页面）
    isInitializing.value = false
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

onMounted(() => {
  if (!scriptId) {
    message.error(t('edit.missingScriptIdParameter'))
    handleCancel()
    return
  }

  loadScriptInfo()
})

onUnmounted(() => {
  // 退出编辑页：归档 MAS 字段终态（MAS 侧修改一定发生在 MAS 内，退出即备份）
  void ensureBackup('mas')
})
</script>

<style scoped>
.user-edit-content {
  max-width: 1200px;
  margin: 0 auto;
}

.config-card {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.config-form {
  max-width: none;
}

.whimbox-preview-box {
  margin-top: 8px;
}

.whimbox-preview-section {
  margin: 12px 0 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.whimbox-preview-section:first-child {
  margin-top: 0;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .user-edit-content {
    max-width: 100%;
  }
}
</style>
