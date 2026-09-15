<template>
  <div class="user-edit-container">
    <M9AUserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      :loading="loading"
      @handle-cancel="handleCancel"
    />

    <div class="user-edit-content">
      <a-card class="config-card">
        <a-form
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <BasicInfoSection
            v-model:form-data="formData"
            :loading="loading"
            @save="handleFieldSave"
            @mode-change="handleConfigModeChange"
            @quick-config-change="handleQuickConfigChange"
            @open-restore="restoreOpen = true"
          />

          <TaskQueueSection
            v-if="formData.Info.Mode !== '直控'"
            v-model:task-queue="taskQueue"
            :script-id="scriptId"
            :loading="loading"
          >
            <template #header-actions>
              <a-button size="small" @click="openRestoreModal">
                <template #icon><HistoryOutlined /></template>
                {{ t('edit.configRestoreTitle') }}
              </a-button>
            </template>
          </TaskQueueSection>

          <ExtraScriptSection
            v-model:form-data="formData"
            :loading="loading"
            @save="handleFieldSave"
          />

          <UserNotifyConfig
            v-model="formData.Notify"
            :loading="loading"
            :script-id="scriptId"
            :user-id="userId"
            @save="handleFieldSave"
          />
        </a-form>
      </a-card>
    </div>

    <!-- ══ 配置恢复（通用组件：MAS 用户字段在前、M9A 本体配置在后）══ -->
    <ConfigRestoreSection
      v-model:open="restoreOpen"
      :script-name="M9A_DISPLAY_NAME"
      :targets="restoreTargets"
      :api="restoreApi"
      :user-desc="t('edit.m9aConfigRestoreUserDesc')"
      :script-desc="t('edit.m9aConfigRestoreScriptDesc')"
      :on-restored="handleRestored"
    >
      <!-- mas 备份为字段侧车分区、native 备份为实例折叠列表（ZzzOd 同语义） -->
      <template #preview="{ raw }">
        <!-- native 池：一个实例的摘要与任务详情折在同一个面板里 -->
        <a-collapse
          v-if="previewInstances(raw).length"
          class="m9a-preview-collapse"
          :bordered="false"
        >
          <a-collapse-panel v-for="inst in previewInstances(raw)" :key="inst.name">
            <template #header>
              <span class="m9a-preview-instance-name">{{ inst.name }}</span>
            </template>
            <a-descriptions
              v-if="inst.rows && inst.rows.length"
              :column="1"
              size="small"
              bordered
              class="m9a-preview-box"
            >
              <a-descriptions-item v-for="row in inst.rows" :key="row.key" :label="row.key">
                {{ row.value }}
              </a-descriptions-item>
            </a-descriptions>
            <div v-for="g in inst.details ?? []" :key="g.name" class="m9a-preview-group">
              <div class="m9a-preview-group-name">{{ g.name }}</div>
              <a-descriptions :column="1" size="small" bordered class="m9a-preview-box">
                <a-descriptions-item v-for="row in g.rows" :key="row.key" :label="row.key">
                  {{ row.value }}
                </a-descriptions-item>
              </a-descriptions>
            </div>
          </a-collapse-panel>
        </a-collapse>
        <!-- mas 池：分区渲染（MAS 独有 / M9A 配置 / 任务配置详情） -->
        <a-empty
          v-else-if="!previewSections(raw).length"
          :description="t('edit.configRestorePreviewEmpty')"
        />
        <div v-else>
          <template v-for="s in previewSections(raw)" :key="s.name">
            <h4 class="m9a-preview-title">{{ s.label }}</h4>
            <a-descriptions
              v-if="s.rows && s.rows.length"
              :column="1"
              size="small"
              bordered
              class="m9a-preview-box"
            >
              <a-descriptions-item v-for="row in s.rows" :key="row.key" :label="row.key">
                {{ row.value }}
              </a-descriptions-item>
            </a-descriptions>
            <div v-for="g in s.groups ?? []" :key="`${s.name}-${g.name}`" class="m9a-preview-group">
              <div class="m9a-preview-group-name">{{ g.name }}</div>
              <a-descriptions :column="1" size="small" bordered class="m9a-preview-box">
                <a-descriptions-item v-for="row in g.rows" :key="row.key" :label="row.key">
                  {{ row.value }}
                </a-descriptions-item>
              </a-descriptions>
            </div>
          </template>
        </div>
      </template>
    </ConfigRestoreSection>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { HistoryOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { useSaveQueue } from '@/composables/useSaveQueue'
import { Service } from '@/api'
import type { M9ATaskQueueItem } from '@/types/script'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'

const logger = window.electronAPI.getLogger('M9A用户编辑')

import M9AUserEditHeader from '../../M9AUserEdit/M9AUserEditHeader.vue'
import BasicInfoSection from '../../M9AUserEdit/BasicInfoSection.vue'
import TaskQueueSection from '../../M9AUserEdit/TaskQueueSection.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'

const { t } = useI18n()

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)
const isInitializing = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { enqueue } = useSaveQueue()

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)

const scriptName = ref('')
const taskQueue = ref<M9ATaskQueueItem[]>([])

const getDefaultM9AUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    Mode: '用户',
    IfQuickConfig: true,
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
    Tag: '',
    Resource: '官服',
    Account: '',
  },
  Task: {
    AvailableTasks: '[]',
    Queue: '[]',
  },
  Notify: {
    Enabled: false,
    ToAddress: '',
    IfSendMail: false,
    IfSendSixStar: false,
    IfSendStatistic: false,
    IfServerChan: false,
    ServerChanKey: '',
    ServerChanChannel: '',
    ServerChanTag: '',
  },
  Data: {
    LastProxyDate: '',
    ProxyTimes: 0,
  },
})

const formData = reactive({
  userName: '',
  ...getDefaultM9AUserData(),
})

const rules = computed(() => {
  const baseRules: Record<string, Rule[]> = {
    userName: [
      { required: true, message: t('edit.enterUsername'), trigger: 'blur' },
      { min: 1, max: 50, message: t('edit.usernameMustBe1'), trigger: 'blur' },
    ],
  }
  return baseRules
})

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

watch(
  () => taskQueue.value,
  newVal => {
    if (!isInitializing.value && userId) {
      handleFieldSave('Task.Queue', JSON.stringify(newVal))
    }
  },
  { deep: true }
)

const handleFieldSave = async (key: string, value: any) => {
  if (isInitializing.value || !userId) return

  await enqueue(async () => {
    try {
      const parts = key.split('.')
      let userData: Record<string, any> = {}
      let current = userData

      for (let i = 0; i < parts.length - 1; i++) {
        current[parts[i]] = {}
        current = current[parts[i]]
      }
      current[parts[parts.length - 1]] = value

      if (key === 'userName') {
        userData = { Info: { Name: value } }
      }

      await updateUser(scriptId, userId, userData)
      logger.info(`用户配置已保存: ${key}`)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存失败: ${errorMsg}`)
    }
  }, key)
}

// 快速配置开关：与配置来源独立，真实保存
const handleQuickConfigChange = async (value: boolean) => {
  formData.Info.IfQuickConfig = value
  await handleFieldSave('Info.IfQuickConfig', value)
}

// 配置来源切换：校验 value ∈ options → 赋值 Info.Mode → 保存
const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['脚本', '用户', '直控'].includes(value)) return
  formData.Info.Mode = value as '脚本' | '用户' | '直控'
  await handleFieldSave('Info.Mode', formData.Info.Mode)
}

const loadScriptInfo = async () => {
  try {
    const script = await getScript(scriptId)
    if (script) {
      scriptName.value = script.name

      if (isEdit.value) {
        await loadUserData()
      } else {
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

const createUserImmediately = async () => {
  try {
    const result = await addUser(scriptId)
    if (result && result.userId) {
      userId = result.userId
      isEdit.value = true
      router.replace({
        name: route.name || undefined,
        params: { ...route.params, userId: result.userId },
      })
      logger.info(`用户已创建，ID: ${result.userId}`)
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
    const userResponse = await getUsers(scriptId, userId)

    if (userResponse && userResponse.code === 200) {
      const userIndex = userResponse.index.find(index => index.uid === userId)
      if (userIndex && userResponse.data[userId]) {
        const userData = userResponse.data[userId] as any

        if (userIndex.type === 'M9AUserConfig') {
          Object.assign(formData, {
            Info: { ...getDefaultM9AUserData().Info, ...userData.Info },
            Task: { ...getDefaultM9AUserData().Task, ...userData.Task },
            Notify: { ...getDefaultM9AUserData().Notify, ...userData.Notify },
            Data: { ...getDefaultM9AUserData().Data, ...userData.Data },
          })

          if (userData.Task?.Queue) {
            try {
              const RESERVED_TASK_NAMES = ['启动游戏', '关闭游戏', '切换账号']
              const parsedQueue = JSON.parse(userData.Task.Queue)
              taskQueue.value = parsedQueue.filter(
                (item: M9ATaskQueueItem) => !RESERVED_TASK_NAMES.includes(item.name)
              )
            } catch {
              taskQueue.value = []
            }
          }
        }

        await nextTick()
        formData.userName = formData.Info.Name || ''

        logger.info('用户数据加载成功')
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
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

// ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
// 专项统一名（文案参数化用）：M9A 统一叫「m9a」
const M9A_DISPLAY_NAME = 'm9a'
const restoreOpen = ref(false)

// 目标池顺序 = segmented 展示顺序：MAS 用户字段（在前）、M9A 本体配置（在后）
const restoreTargets: Array<{ key: string; kind: 'user' | 'script' }> = [
  { key: 'mas', kind: 'user' },
  { key: 'native', kind: 'script' },
]

// 组件调用后端：通用 /backup/* 端点（脚本/用户上下文在此闭包捕获）
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

// 预览响应原文（unknown）收敛为分区视图：泛用组件的 raw 插槽不带专项类型
interface M9APreviewRow {
  key: string
  value: string
}
interface M9APreviewSection {
  name: string
  label: string
  rows?: M9APreviewRow[]
  groups?: Array<{ name: string; rows: M9APreviewRow[] }>
}
const previewSections = (raw: unknown): M9APreviewSection[] =>
  (raw as { sections?: M9APreviewSection[] } | null)?.sections ?? []

interface M9APreviewInstance {
  name: string
  rows: M9APreviewRow[]
  details?: Array<{ name: string; rows: M9APreviewRow[] }>
}
const previewInstances = (raw: unknown): M9APreviewInstance[] =>
  (raw as { instances?: M9APreviewInstance[] } | null)?.instances ?? []

// 一键恢复成功：mas 恢复含任务队列与页面字段回填，重拉表单——否则旧表单值
// 在下次保存时会静默覆盖恢复结果；native 恢复不影响本页表单
const handleRestored = async (target: string) => {
  restoreOpen.value = false
  if (target === 'mas') {
    // 暂停 watch 自动保存，避免加载过程中把恢复值原样写回一遍
    isInitializing.value = true
    await loadUserData()
  }
}

// 编辑界面归档（进入/退出时机，指纹去重）：进入归档 M9A 本体配置当前状态
// （MAS 触碰前原始态，用户可能刚在 M9A GUI 里改过），退出归档 MAS 编辑页
// 核心字段终态；运行前归档由 manager.prepare 在任务级完成
const ensureM9ABackup = async (target: 'mas' | 'native') => {
  if (!userId) return
  try {
    await Service.ensureConfigBackupApiApiScriptsBackupEnsurePost({
      scriptId,
      userId,
      target,
    })
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

onMounted(async () => {
  if (!scriptId) {
    message.error(t('edit.missingScriptIdParameter'))
    handleCancel()
    return
  }

  // 先等脚本信息与用户就绪（新建模式内部会创建用户并写入 userId）再归档，
  // 否则新建用户首次进入会因 userId 未就绪静默跳过归档
  await loadScriptInfo()
  await nextTick()
  void ensureM9ABackup('native')
})

onUnmounted(() => {
  // 退出编辑页：归档 MAS 编辑页核心字段终态（M9A 无遮罩会话，无需停会话）
  void ensureM9ABackup('mas')
})
</script>

<style scoped>
.user-edit-container {
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

.user-edit-content {
  max-width: 1400px;
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

/* ══ 配置恢复预览（分区标题 + 表格 + 任务详情分组）══ */
.m9a-preview-title {
  margin: 16px 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.m9a-preview-title:first-of-type {
  margin-top: 0;
}

.m9a-preview-group {
  margin-top: 12px;
}

.m9a-preview-group-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
  margin-bottom: 4px;
}

.m9a-preview-box {
  width: 100%;
}

.m9a-preview-collapse :deep(.ant-collapse-header) {
  padding-left: 0;
}

.m9a-preview-instance-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .user-edit-content {
    max-width: 100%;
  }
}
</style>
