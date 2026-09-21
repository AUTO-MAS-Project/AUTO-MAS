<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit/mss`" class="breadcrumb-link">
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
            <a-col :span="8">
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
            <a-col :span="4">
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
            <a-col :span="4">
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
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.mssUserTagHint')">
                    <span class="form-label">
                      {{ t('edit.mssUserTag') }}
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

          <a-row :gutter="24">
            <a-col :span="24">
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
          </a-row>
        </div>

        <!-- 可用任务：清单由本软件在运行前从 MSS 的 interface.json 同步 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.mssAvailableTasks') }}</h3>
          </div>
          <a-alert
            v-if="!availableTasks.length"
            type="info"
            show-icon
            :message="t('edit.mssAvailableTasksEmpty')"
          />
          <div v-else class="task-picker">
            <div class="task-picker-hint">{{ t('edit.mssAvailableTasksHint') }}</div>
            <a-row :gutter="[16, 8]">
              <a-col v-for="task in availableTasks" :key="taskKey(task)" :span="12">
                <a-checkbox
                  :checked="isTaskQueued(task)"
                  :disabled="loading || !userId"
                  @change="() => toggleTask(task)"
                >
                  <span class="task-picker-name">{{ task.name || task.entry }}</span>
                  <span v-if="task.description" class="task-picker-desc">
                    {{ task.description }}
                  </span>
                </a-checkbox>
              </a-col>
            </a-row>
          </div>
        </div>

        <!-- 任务队列：顺序即执行顺序，选项值按队列写进实例配置 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.taskQueue') }}</h3>
          </div>
          <div class="task-picker-hint">{{ t('edit.mssTaskQueueHint') }}</div>
          <a-empty v-if="!taskQueue.length" :description="t('edit.mssQueueEmpty')" />
          <div v-else class="queue-list">
            <div v-for="(item, index) in taskQueue" :key="`${taskKey(item)}-${index}`" class="queue-item">
              <div class="queue-item-head">
                <span class="queue-index">{{ index + 1 }}</span>
                <span class="queue-name">{{ item.name || item.entry }}</span>
                <a-space size="small">
                  <a-button
                    size="small"
                    :title="t('edit.moveTaskUp')"
                    :disabled="loading || index === 0"
                    @click="moveQueueItem(index, -1)"
                  >
                    <template #icon><ArrowUpOutlined /></template>
                  </a-button>
                  <a-button
                    size="small"
                    :title="t('edit.moveTaskDown')"
                    :disabled="loading || index === taskQueue.length - 1"
                    @click="moveQueueItem(index, 1)"
                  >
                    <template #icon><ArrowDownOutlined /></template>
                  </a-button>
                  <a-button size="small" danger :disabled="loading" @click="removeQueueItem(index)">
                    <template #icon><DeleteOutlined /></template>
                  </a-button>
                </a-space>
              </div>
              <div v-if="taskOptionNames(item).length" class="queue-options">
                <div v-for="optionName in taskOptionNames(item)" :key="optionName" class="queue-option">
                  <span class="queue-option-name">{{ optionName }}</span>
                  <a-input
                    :value="formatOptionValue(item.options[optionName])"
                    :disabled="loading || !userId"
                    :placeholder="t('edit.mssOptionValueHint')"
                    class="modern-input"
                    @blur="handleOptionBlur(index, optionName, $event)"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 数据统计（只读，由本软件自动写入） -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.statistics') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.mssLastProxyDate') }}
                    <a-tooltip :title="t('edit.mssDataReadOnlyHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input :value="formData.Data.LastProxyDate" readonly size="large" />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.mssProxyTimes') }}
                    <a-tooltip :title="t('edit.mssDataReadOnlyHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input :value="formData.Data.ProxyTimes" readonly size="large" />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <ExtraScriptSection v-model:form-data="formData" :loading="loading" @save="handleFieldSave" />

        <UserNotifyConfig
          v-model="formData.Notify"
          :loading="loading"
          :script-id="scriptId"
          :user-id="userId"
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
import {
  ArrowDownOutlined,
  ArrowLeftOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { parseStatusTagList } from '@/composables/useStatusTag.ts'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import type {
  MSSAvailableTaskItem,
  MSSQueuedTaskItem,
  MSSTaskOptionValue,
} from '@/types/script'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('MSS用户编辑')

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)
const isInitializing = ref(true) // 标记是否正在初始化
const isSaving = ref(false) // 标记是否正在保存

// 路由参数
const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId) // 使用 ref 以便在创建后更新
const { configLocked } = useScriptConfigLock(() => scriptId)

// 脚本信息
const scriptName = ref('')

// 可用任务（后端写入 Task.AvailableTasks）、任务队列（本页写入 Task.Queue）
const availableTasks = ref<MSSAvailableTaskItem[]>([])
const taskQueue = ref<MSSQueuedTaskItem[]>([])

// MSS 用户默认数据（与后端 MSSUserConfig 的默认值保持一致）
const getDefaultMSSUserData = () => ({
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
  },
  Task: {
    AvailableTasks: '[]',
    Queue: '[]',
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
  },
  Data: {
    LastProxyDate: '',
    ProxyTimes: 0,
  },
})

// 创建扁平化的表单数据，用于表单验证
const formData = reactive({
  // 扁平化的验证字段
  userName: '',
  // 嵌套的实际数据
  ...getDefaultMSSUserData(),
})

// 只读标签：后端按运行情况生成的 JSON 字符串
const userTags = computed(() => parseStatusTagList(formData.Info.Tag))

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

// ══ 任务队列 ══
// AvailableTasks / Queue 在配置里都是 JSON 数组字符串（后端也可能直接给数组）
const parseConfigList = <T,>(raw: unknown): T[] => {
  if (Array.isArray(raw)) return raw as T[]
  if (typeof raw !== 'string' || !raw.trim()) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as T[]) : []
  } catch {
    return []
  }
}

const taskKey = (task: Pick<MSSAvailableTaskItem, 'name' | 'entry'>) =>
  task.entry || task.name || ''

/** 队列项与清单项算同一个任务：entry 优先，缺失时退回显示名 */
const isSameTask = (
  item: Pick<MSSQueuedTaskItem, 'name' | 'entry'>,
  task: Pick<MSSAvailableTaskItem, 'name' | 'entry'>
) => (task.entry && item.entry ? task.entry === item.entry : task.name === item.name)

const isTaskQueued = (task: MSSAvailableTaskItem) =>
  taskQueue.value.some(item => isSameTask(item, task))

/** 队列项的选项名来自清单里的任务定义；清单缺失（未运行过）时不显示选项编辑 */
const taskOptionNames = (item: MSSQueuedTaskItem): string[] => {
  const matched = availableTasks.value.find(task => isSameTask(item, task))
  return matched?.option ?? []
}

const formatOptionValue = (value: MSSTaskOptionValue | undefined): string => {
  if (value === undefined) return ''
  return typeof value === 'string' ? value : JSON.stringify(value)
}

// 队列整体落盘：选项编辑与排序都走这里，Task.Queue 只提交一次
const saveQueue = async (next: MSSQueuedTaskItem[]) => {
  taskQueue.value = next
  await handleFieldSave('Task.Queue', JSON.stringify(next))
}

const toggleTask = async (task: MSSAvailableTaskItem) => {
  if (loading.value || !userId) return
  if (isTaskQueued(task)) {
    await saveQueue(taskQueue.value.filter(item => !isSameTask(item, task)))
    return
  }
  await saveQueue([
    ...taskQueue.value,
    { name: task.name || task.entry, entry: task.entry || '', options: {} },
  ])
}

const moveQueueItem = async (index: number, delta: number) => {
  const target = index + delta
  if (target < 0 || target >= taskQueue.value.length) return
  const next = [...taskQueue.value]
  const [moved] = next.splice(index, 1)
  next.splice(target, 0, moved)
  await saveQueue(next)
}

const removeQueueItem = async (index: number) => {
  const next = [...taskQueue.value]
  next.splice(index, 1)
  await saveQueue(next)
}

// 选项取值：选择型（select）填选项名，输入型（input）填 JSON 对象
// {"输入名": "值"}；清空表示沿用 MSS 里的默认值
const applyOptionValue = async (index: number, optionName: string, raw: string) => {
  const current = taskQueue.value[index]
  if (!current) return

  const text = raw.trim()
  const options: Record<string, MSSTaskOptionValue> = { ...current.options }

  if (!text) {
    delete options[optionName]
  } else if (text.startsWith('{')) {
    let parsed: unknown
    try {
      parsed = JSON.parse(text)
    } catch {
      message.error(t('edit.mssOptionValueHint'))
      return
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      message.error(t('edit.mssOptionValueHint'))
      return
    }
    options[optionName] = parsed as Record<string, string>
  } else {
    options[optionName] = text
  }

  await saveQueue(
    taskQueue.value.map((item, i) => (i === index ? { ...item, options } : item))
  )
}

const handleOptionBlur = (index: number, optionName: string, event: Event) => {
  const target = event.target as HTMLInputElement | null
  void applyOptionValue(index, optionName, target?.value ?? '')
}

// 即时保存单个字段变更（局部更新，不整体覆盖用户配置）
const handleFieldSave = async (key: string, value: any) => {
  if (isInitializing.value || isSaving.value || !userId) return

  isSaving.value = true
  try {
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

    await updateUser(scriptId, userId, userData)
    logger.info(`用户配置已保存: ${key}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

// 加载脚本信息
const loadScriptInfo = async () => {
  try {
    const script = await getScript(scriptId)
    if (script) {
      scriptName.value = script.name

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
  if (configLocked.value) return false

  try {
    const result = await addUser(scriptId)
    if (result && result.userId) {
      userId = result.userId
      isEdit.value = true
      // 更新路由，但不刷新页面
      router.replace({
        name: route.name || undefined,
        params: { ...route.params, userId: result.userId },
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

        // 填充 MSS 用户数据
        if (userIndex.type === 'MSSUserConfig') {
          Object.assign(formData, {
            Info: { ...getDefaultMSSUserData().Info, ...userData.Info },
            Notify: { ...getDefaultMSSUserData().Notify, ...userData.Notify },
            Data: { ...getDefaultMSSUserData().Data, ...userData.Data },
            Task: { ...getDefaultMSSUserData().Task, ...userData.Task },
          })
          availableTasks.value = parseConfigList<MSSAvailableTaskItem>(
            userData.Task?.AvailableTasks
          )
          taskQueue.value = parseConfigList<MSSQueuedTaskItem>(userData.Task?.Queue)
        }

        // 同步扁平化字段 - 使用nextTick确保数据更新完成后再同步
        await nextTick()
        formData.userName = formData.Info.Name || ''

        logger.info('用户数据加载成功')

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
  await nextTick()
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

.task-picker-hint {
  margin: 8px 0 12px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.task-picker-name {
  font-weight: 600;
}

.task-picker-desc {
  margin-left: 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.queue-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.queue-item {
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 12px 16px;
  background: var(--ant-color-bg-container);
}

.queue-item-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.queue-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-size: 13px;
  font-weight: 600;
}

.queue-name {
  flex: 1;
  font-weight: 600;
  color: var(--ant-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue-options {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.queue-option {
  display: flex;
  align-items: center;
  gap: 12px;
}

.queue-option-name {
  flex: 0 0 180px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

/* 响应式设计 */
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
