<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit/okscript`" class="breadcrumb-link">
            {{ scriptName }}
          </router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          {{ isEdit ? t('comp.editUser') : t('comp.addUser2') }}
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        {{ t('edit.back') }}
      </a-button>
    </a-space>
  </div>

  <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
    <a-card class="config-card">
      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <!-- 基本信息 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.basicInfo') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item name="userName" required>
                <template #label>
                  <a-tooltip :title="t('edit.displayNameUsedIdentify')">
                    <span class="form-label">
                      {{ t('edit.username') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input
                  v-model:value="formData.userName"
                  :placeholder="t('edit.enterUsername')"
                  :disabled="loading"
                  size="large"
                  class="modern-input"
                  @blur="handleFieldSave('userName', formData.userName)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item name="status">
                <template #label>
                  <a-tooltip :title="t('edit.whetherThisUserEnabled')">
                    <span class="form-label">
                      {{ t('edit.enabled') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="formData.Info.Status"
                  :disabled="loading"
                  size="large"
                  style="width: 100%"
                  @change="handleFieldSave('Info.Status', formData.Info.Status)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item name="remainedDay">
                <template #label>
                  <a-tooltip :title="t('edit.daysLeftAccount1')">
                    <span class="form-label">
                      {{ t('edit.daysLeft') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="formData.Info.RemainedDay"
                  :min="-1"
                  :max="9999"
                  placeholder="-1"
                  :disabled="loading"
                  size="large"
                  style="width: 100%"
                  @blur="handleFieldSave('Info.RemainedDay', formData.Info.RemainedDay)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="24">
              <a-form-item name="taskId">
                <template #label>
                  <a-tooltip :title="t('edit.okscriptTaskHint')">
                    <span class="form-label">
                      {{ t('edit.okscriptTask') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  :value="formData.Task.TaskId || undefined"
                  :placeholder="t('edit.okscriptTaskPlaceholder')"
                  :disabled="loading || !project"
                  :loading="probing"
                  :options="taskOptions"
                  size="large"
                  show-search
                  option-filter-prop="label"
                  style="width: 100%"
                  @change="handleTaskChange"
                />
              </a-form-item>
              <a-alert
                v-if="probeError"
                type="warning"
                show-icon
                :message="probeError"
                class="task-alert"
              />
              <a-alert
                v-else-if="taskMissing"
                type="warning"
                show-icon
                :message="t('edit.okscriptTaskMissing', { name: formData.Task.TaskName })"
                class="task-alert"
              />
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="16">
              <a-form-item name="notes">
                <template #label>
                  <a-tooltip :title="t('edit.addNoteAboutThis')">
                    <span class="form-label">
                      {{ t('edit.note') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-textarea
                  v-model:value="formData.Info.Notes"
                  :placeholder="t('edit.enterNote3')"
                  :rows="3"
                  :disabled="loading"
                  class="modern-input"
                  @blur="handleFieldSave('Info.Notes', formData.Info.Notes)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.okscriptUserTagHint')">
                    <span class="form-label">
                      {{ t('edit.okscriptUserTag') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <div class="user-tag-list">
                  <a-tag
                    v-for="(tag, index) in userTags"
                    :key="index"
                    :title="tag.text"
                    :color="tag.color"
                  >
                    {{ tag.text }}
                  </a-tag>
                </div>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 数据统计（只读，由本软件自动写入） -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.statistics') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.okscriptLastProxyDate') }}
                    <a-tooltip :title="t('edit.okscriptDataReadOnlyHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input :value="formData.Data.LastProxyDate" readonly size="large" />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.okscriptProxyTimes') }}
                    <a-tooltip :title="t('edit.okscriptDataReadOnlyHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input :value="formData.Data.ProxyTimes" readonly size="large" />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.okscriptLastProxyStatus') }}
                    <a-tooltip :title="t('edit.okscriptDataReadOnlyHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input :value="formData.Data.LastProxyStatus" readonly size="large" />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <UserNotifyConfig
          v-model="formData.Notify"
          :loading="loading"
          :script-id="scriptId"
          :user-id="currentUserId"
          @save="handleFieldSave"
        />
      </a-form>
    </a-card>
  </ConfigLockPanel>
</template>

<script setup lang="ts">
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { useI18n } from 'vue-i18n'
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { parseStatusTagList } from '@/composables/useStatusTag.ts'
import {
  OkScriptService,
  type OkScriptProjectInfo,
  type OkScriptTaskItem,
  type UserUpdateIn,
} from '@/api'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('OkScript用户编辑')

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)
const isInitializing = ref(true)
const isSaving = ref(false)

// 路由参数
const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const currentUserId = ref<string | null>(userId || null)
const isEdit = ref(!!userId)
const { configLocked } = useScriptConfigLock(() => scriptId)

const scriptName = ref('')

// 与后端 OkScriptUserConfig 的默认值保持一致
const getDefaultOkScriptUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    RemainedDay: -1,
    Notes: '',
    Tag: '',
  },
  Task: {
    TaskId: '',
    TaskName: '',
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

const formData = reactive({
  userName: '',
  ...getDefaultOkScriptUserData(),
})

// 任务候选：按脚本的安装目录实时识别，项目升级后列表随之变化
const project = ref<OkScriptProjectInfo | null>(null)
const probeError = ref('')
const probing = ref(false)

const taskLabel = (task: OkScriptTaskItem) =>
  task.continuous
    ? `${task.index}. ${task.name}（${t('edit.okscriptContinuousTask')}）`
    : `${task.index}. ${task.name}`

const taskOptions = computed(() =>
  (project.value?.tasks ?? []).map(task => ({
    label: taskLabel(task),
    value: task.taskId,
    disabled: task.continuous,
  }))
)

const taskMissing = computed(
  () =>
    !!project.value &&
    !!formData.Task.TaskId &&
    !project.value.tasks.some(task => task.taskId === formData.Task.TaskId)
)

const loadProject = async (rootPath: string) => {
  if (!rootPath) {
    probeError.value = t('edit.okscriptRootPathMissing')
    return
  }
  probing.value = true
  try {
    const resp = await OkScriptService.probeOkscriptProjectApiApiScriptsOkscriptProbePost({
      rootPath,
    })
    if (resp.code === 200 && resp.data) {
      project.value = resp.data
      probeError.value = ''
    } else {
      probeError.value = resp.message || t('edit.okscriptProbeFailed')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`识别项目失败: ${errorMsg}`)
    probeError.value = errorMsg
  } finally {
    probing.value = false
  }
}

const userTags = computed(() => parseStatusTagList(formData.Info.Tag))

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

const saveUserData = async (userData: Record<string, unknown>, label: string) => {
  if (isInitializing.value || isSaving.value || !userId) return false
  isSaving.value = true
  try {
    const success = await updateUser(scriptId, userId, userData as UserUpdateIn['data'])
    if (success) logger.info(`用户配置已保存: ${label}`)
    return success
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
    return false
  } finally {
    isSaving.value = false
  }
}

// 即时保存单个字段变更（局部更新，不整体覆盖用户配置）
const handleFieldSave = async (key: string, value: unknown) => {
  // 解析 key 路径，例如 "Info.Status" -> { Info: { Status: value } }
  const parts = key.split('.')
  let userData: Record<string, unknown> = {}
  let current = userData
  for (let i = 0; i < parts.length - 1; i++) {
    const next: Record<string, unknown> = {}
    current[parts[i]] = next
    current = next
  }
  current[parts[parts.length - 1]] = value

  // 特殊处理：userName 需要同步到 Info.Name
  if (key === 'userName') {
    userData = { Info: { Name: value } }
  }

  await saveUserData(userData, key)
}

// 任务 ID 与显示名一起保存：显示名只用于标签，运行时按 ID 对应当前版本的序号
const handleTaskChange = async (value: unknown) => {
  if (configLocked.value || typeof value !== 'string') return
  const task = project.value?.tasks.find(item => item.taskId === value)
  if (!task || task.continuous) return
  const previous = { ...formData.Task }
  formData.Task.TaskId = task.taskId
  formData.Task.TaskName = task.name
  const saved = await saveUserData(
    { Task: { TaskId: task.taskId, TaskName: task.name } },
    'Task.TaskId'
  )
  if (!saved) {
    Object.assign(formData.Task, previous)
  }
}

const loadScriptInfo = async () => {
  try {
    const script = await getScript(scriptId)
    if (script) {
      scriptName.value = script.name
      const rootPath = String(
        (script.config as { Info?: { RootPath?: string } }).Info?.RootPath || ''
      )
      void loadProject(rootPath)

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

// 新增模式下立即创建用户
const createUserImmediately = async () => {
  if (configLocked.value) return false

  try {
    const result = await addUser(scriptId)
    if (result && result.userId) {
      userId = result.userId
      currentUserId.value = result.userId
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
        const userData = userResponse.data[userId] as Partial<
          ReturnType<typeof getDefaultOkScriptUserData>
        >

        if (userIndex.type === 'OkScriptUserConfig') {
          const defaults = getDefaultOkScriptUserData()
          Object.assign(formData, {
            Info: { ...defaults.Info, ...userData.Info },
            Task: { ...defaults.Task, ...userData.Task },
            Notify: { ...defaults.Notify, ...userData.Notify },
            Data: { ...defaults.Data, ...userData.Data },
          })
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

onMounted(async () => {
  if (!scriptId) {
    message.error(t('edit.missingScriptIdParameter'))
    handleCancel()
    return
  }
  await loadScriptInfo()
})
</script>

<style scoped>
.user-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-nav {
  flex: 1;
}

.breadcrumb {
  margin: 0;
}

.breadcrumb-link {
  color: var(--ant-color-text-secondary);
  text-decoration: none;
}

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

.form-section {
  margin-bottom: 12px;
}

.form-section:last-child {
  margin-bottom: 0;
}

.section-header {
  margin-bottom: 6px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.task-alert {
  margin: -12px 0 24px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
}

.modern-input:hover {
  border-color: var(--ant-color-primary-hover);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

.user-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  min-height: 40px;
}

.cancel-button {
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
}

.cancel-button:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

@media (max-width: 768px) {
  .user-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .user-edit-content {
    max-width: 100%;
  }
}
</style>
