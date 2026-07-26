<template>
  <div class="user-edit-container">
    <PageHeader
      :title="formData.userName || (isEdit ? '编辑用户' : '添加用户')"
      :subtitle="`${scriptName} · ok-ww 用户配置`"
      :bordered="false"
      compact
      transparent
    >
      <a-tag color="blue">ok-ww</a-tag>
      <template #actions>
        <a-button class="cancel-button" @click="handleCancel">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          返回
        </a-button>
      </template>
    </PageHeader>

    <div class="user-edit-content">
      <a-spin :spinning="pageLoading" tip="加载用户配置中...">
        <div class="config-surface">
          <a-alert
            v-if="saveError"
            class="save-error"
            type="error"
            show-icon
            :message="saveError"
          />
          <a-form :model="formData" layout="vertical" class="config-form">
            <div class="form-section">
              <div class="section-header">
                <h3>基本信息</h3>
              </div>

              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        用户名
                        <a-tooltip
                          title="用于区分用户的名称，相同名称的用户将被视为同一用户进行统计"
                        >
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-input
                      v-model:value="formData.userName"
                      placeholder="请输入用户名"
                      size="large"
                      class="modern-input"
                      @blur="saveField('Info.Name', formData.userName)"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        启用状态
                        <a-tooltip title="是否启用该用户">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-select
                      v-model:value="formData.Info.Status"
                      size="large"
                      class="modern-select"
                      @change="saveField('Info.Status', formData.Info.Status)"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        账号
                        <a-tooltip title="用于切换账号，无需切换则留空。官服输入 11 位手机号">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-input
                      v-model:value="formData.Info.Id"
                      placeholder="请输入账号"
                      size="large"
                      class="modern-input"
                      @blur="saveField('Info.Id', formData.Info.Id)"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        密码
                        <a-tooltip title="PC 端需要切换账号时必须填写">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-space-compact block>
                      <a-input-password
                        v-model:value="formData.Info.Password"
                        :placeholder="passwordConfigured ? '已配置，留空保持不变' : '请输入密码'"
                        size="large"
                        class="modern-input"
                        @blur="saveField('Info.Password', formData.Info.Password)"
                      />
                      <a-button
                        v-if="passwordConfigured && !formData.Info.Password"
                        danger
                        size="large"
                        :disabled="isSaving"
                        @click="confirmClearSensitiveField('Info.Password')"
                      >
                        清空原值
                      </a-button>
                    </a-space-compact>
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        游戏资源
                        <a-tooltip title="选择当前用户使用的游戏资源">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-select
                      v-model:value="formData.Info.Resource"
                      placeholder="请选择资源"
                      size="large"
                      class="modern-select"
                      :options="resourceOptions"
                      @change="saveField('Info.Resource', formData.Info.Resource)"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        剩余天数
                        <a-tooltip title="账号剩余的有效天数，「-1」表示无限">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-input-number
                      v-model:value="formData.Info.RemainedDay"
                      :min="-1"
                      :max="9999"
                      size="large"
                      style="width: 100%"
                      @blur="saveField('Info.RemainedDay', formData.Info.RemainedDay)"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-form-item>
                <template #label>
                  <span class="form-label">
                    备注
                    <a-tooltip title="为用户添加备注信息">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-textarea
                  v-model:value="formData.Info.Notes"
                  placeholder="请输入备注"
                  :rows="4"
                  class="modern-input"
                  @blur="saveField('Info.Notes', formData.Info.Notes)"
                />
              </a-form-item>
            </div>
          </a-form>

          <!-- OK-WW 配置编辑器 -->
          <a-form :model="formData" layout="vertical" class="config-form">
            <div class="form-section">
              <div class="section-header">
                <h3>任务配置</h3>
              </div>

              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        启动任务（-t N）
                        <a-tooltip title="任务序号与 ok-ww 任务列表一致">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-select
                      v-model:value="formData.Task.TaskIndex"
                      size="large"
                      @change="handleTaskIndexChange"
                    >
                      <a-select-option
                        v-for="item in okwwTaskOptions"
                        :key="item.value"
                        :value="item.value"
                      >
                        {{ item.label }}
                      </a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        当前启动参数
                        <a-tooltip title="参数由任务配置自动生成，固定追加 -e">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-input
                      :value="currentStartupArguments"
                      size="large"
                      readonly
                      class="modern-input"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
            </div>
          </a-form>

          <section class="editor-section">
            <OkScriptConfigEditor
              v-if="userId"
              :script-id="scriptId"
              :user-id="userId"
              endpoint-prefix="/plugin/okww/configs"
              @saved="handleConfigSaved"
              @unavailable="goBackToScriptEdit"
            />
          </section>

          <a-form :model="formData" layout="vertical" class="config-form">
            <ExtraScriptSection :form-data="formData" :loading="pageLoading" @save="saveField" />
          </a-form>

          <a-form :model="formData" layout="vertical" class="config-form">
            <div class="form-section">
              <div class="section-header">
                <h3>通知配置</h3>
              </div>
              <a-row :gutter="24" align="middle">
                <a-col :span="6">
                  <span style="font-weight: 500">启用通知</span>
                </a-col>
                <a-col :span="18">
                  <a-switch
                    v-model:checked="formData.Notify.Enabled"
                    @change="saveField('Notify.Enabled', formData.Notify.Enabled)"
                  />
                </a-col>
              </a-row>

              <a-row :gutter="24" style="margin-top: 16px">
                <a-col :span="6">
                  <span style="font-weight: 500">通知内容</span>
                </a-col>
                <a-col :span="18">
                  <a-checkbox
                    v-model:checked="formData.Notify.IfSendStatistic"
                    :disabled="!formData.Notify.Enabled"
                    @change="saveField('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)"
                  >
                    统计信息
                  </a-checkbox>
                </a-col>
              </a-row>

              <a-row :gutter="24" style="margin-top: 16px">
                <a-col :span="6">
                  <a-checkbox
                    v-model:checked="formData.Notify.IfSendMail"
                    :disabled="!formData.Notify.Enabled"
                    @change="saveField('Notify.IfSendMail', formData.Notify.IfSendMail)"
                  >
                    邮件通知
                  </a-checkbox>
                </a-col>
                <a-col :span="18">
                  <a-input
                    v-model:value="formData.Notify.ToAddress"
                    placeholder="请输入收件邮箱"
                    :disabled="!formData.Notify.Enabled || !formData.Notify.IfSendMail"
                    size="large"
                    @blur="saveField('Notify.ToAddress', formData.Notify.ToAddress)"
                  />
                </a-col>
              </a-row>

              <a-row :gutter="24" style="margin-top: 16px">
                <a-col :span="6">
                  <a-checkbox
                    v-model:checked="formData.Notify.IfServerChan"
                    :disabled="!formData.Notify.Enabled"
                    @change="saveField('Notify.IfServerChan', formData.Notify.IfServerChan)"
                  >
                    Server酱
                  </a-checkbox>
                </a-col>
                <a-col :span="18">
                  <a-space-compact block>
                    <a-input-password
                      v-model:value="formData.Notify.ServerChanKey"
                      :placeholder="
                        serverChanKeyConfigured ? '已配置，留空保持不变' : '请输入 SENDKEY'
                      "
                      :disabled="!formData.Notify.Enabled || !formData.Notify.IfServerChan"
                      size="large"
                      @blur="saveField('Notify.ServerChanKey', formData.Notify.ServerChanKey)"
                    />
                    <a-button
                      v-if="serverChanKeyConfigured && !formData.Notify.ServerChanKey"
                      danger
                      size="large"
                      :disabled="isSaving"
                      @click="confirmClearSensitiveField('Notify.ServerChanKey')"
                    >
                      清空原值
                    </a-button>
                  </a-space-compact>
                </a-col>
              </a-row>

              <div style="margin-top: 16px">
                <WebhookManager mode="user" :script-id="scriptId" :user-id="userId" />
              </div>
            </div>
          </a-form>
        </div>
      </a-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/mac/PageHeader.vue'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { useOkScriptConfigApi } from '@/composables/useOkScriptConfigApi'
import WebhookManager from '@/components/WebhookManager.vue'
import OkScriptConfigEditor from '@/views/OkScriptUserEdit/OkScriptConfigEditor.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'

const logger = window.electronAPI.getLogger('ok-ww用户编辑')
const route = useRoute()
const router = useRouter()
const api = useScriptRegistryApi()
const okwwConfigApi = useOkScriptConfigApi('/plugin/okww/configs')

const scriptId = route.params.scriptId as string
const userId = ref((route.params.userId as string) || '')
const isEdit = ref(!!userId.value)
const scriptName = ref('ok-ww脚本')

const pageLoading = ref(true)
const isInitializing = ref(true)
const isSaving = ref(false)
const saveError = ref('')
const passwordConfigured = ref(false)
const serverChanKeyConfigured = ref(false)

const resourceOptions = [{ label: '官服', value: '官服' }]

// 任务序号下拉动态来自后端 /plugin/okww/configs/list（跟随 ok-ww 版本与内置 i18n）。
// 下方静态表仅作纯安装态（无 repo 源码）或动态加载失败时的兜底默认。
// ponytail: 静态兜底，动态列表非空即整体覆盖
const okwwTaskOptions = ref<Array<{ value: number; label: string }>>([
  { label: '1 - DailyTask（日常）', value: 1 },
  { label: '2 - MultiAccountDailyTask（多账号日常）', value: 2 },
  { label: '3 - FarmEchoTask（刷声骸）', value: 3 },
  { label: '4 - AutoRogueTask（半自动肉鸽）', value: 4 },
  { label: '5 - ForgeryTask（凝素领域）', value: 5 },
  { label: '6 - NightmareNestTask（梦魇巢穴）', value: 6 },
  { label: '7 - SimulationTask（模拟领域）', value: 7 },
  { label: '8 - TacetTask（无音区）', value: 8 },
])

interface OkwwUserInfoForm {
  Name: string
  Status: boolean
  Id: string
  Password: string
  Mode: '详细'
  Resource: '官服'
  RemainedDay: number
  IfScriptBeforeTask: boolean
  ScriptBeforeTask: string
  IfScriptAfterTask: boolean
  ScriptAfterTask: string
  Notes: string
}

interface OkwwUserTaskForm {
  TaskIndex: number
}

interface OkwwUserNotifyForm {
  Enabled: boolean
  IfSendStatistic: boolean
  IfSendMail: boolean
  ToAddress: string
  IfServerChan: boolean
  ServerChanKey: string
  CustomWebhooks: any[]
}

interface OkwwUserDataForm {
  LastProxyDate: string
  ProxyTimes: number
}

interface OkwwUserFormData {
  userName: string
  Info: OkwwUserInfoForm
  Task: OkwwUserTaskForm
  Notify: OkwwUserNotifyForm
  Data: OkwwUserDataForm
}

const getDefaultUserData = (): Omit<OkwwUserFormData, 'userName'> => ({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    Mode: '详细',
    Resource: '官服',
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
  },
  Task: {
    TaskIndex: 1,
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
    CustomWebhooks: [],
  },
  Data: {
    LastProxyDate: '',
    ProxyTimes: 0,
  },
})

const formData = reactive<OkwwUserFormData>({
  userName: '',
  ...getDefaultUserData(),
})

const currentStartupArguments = computed(() => `-t ${formData.Task.TaskIndex || 1} -e`)

const handleCancel = () => router.push('/scripts')

const createUserImmediately = async () => {
  const created = await api.addUser(scriptId)
  if (!created?.id) {
    throw new Error('创建用户失败')
  }
  userId.value = created.id
  isEdit.value = true
  await router.replace({
    name: 'OkwwUserEdit',
    params: { scriptId, userId: userId.value },
  })
}

const saveField = async (key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value || !userId.value) return
  if ((key === 'Info.Password' || key === 'Notify.ServerChanKey') && !String(value || '').trim()) {
    return
  }

  isSaving.value = true
  saveError.value = ''
  try {
    const parts = key.split('.')
    const patch: Record<string, any> = {}
    let current = patch
    for (let i = 0; i < parts.length - 1; i += 1) {
      current[parts[i]] = {}
      current = current[parts[i]]
    }
    current[parts[parts.length - 1]] = value

    if (key === 'Info.Name') {
      formData.userName = String(value || '')
    }

    const updateResult: unknown = await api.updateUser(scriptId, userId.value, patch)
    if (updateResult === false) {
      throw new Error('用户配置保存失败，请检查后端连接')
    }
    if (key === 'Info.Password') {
      passwordConfigured.value = true
      formData.Info.Password = ''
    } else if (key === 'Notify.ServerChanKey') {
      serverChanKeyConfigured.value = true
      formData.Notify.ServerChanKey = ''
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    saveError.value = msg
    logger.error(msg)
    message.error(msg)
  } finally {
    isSaving.value = false
  }
}

type OkwwSensitiveField = 'Info.Password' | 'Notify.ServerChanKey'

const clearSensitiveField = async (key: OkwwSensitiveField) => {
  if (isInitializing.value || isSaving.value || !userId.value) return

  const [group, field] = key.split('.')
  isSaving.value = true
  saveError.value = ''
  try {
    const updateResult: unknown = await api.updateUser(scriptId, userId.value, {
      [group]: { [field]: '' },
    })
    if (updateResult === false) {
      throw new Error('敏感配置清空失败，请检查后端连接')
    }
    if (key === 'Info.Password') {
      passwordConfigured.value = false
      formData.Info.Password = ''
    } else {
      serverChanKeyConfigured.value = false
      formData.Notify.ServerChanKey = ''
    }
    message.success('敏感配置已清空')
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error)
    saveError.value = msg
    logger.error(`敏感配置清空失败: ${key}`)
    message.error(msg)
    throw error
  } finally {
    isSaving.value = false
  }
}

const confirmClearSensitiveField = (key: OkwwSensitiveField) => {
  Modal.confirm({
    title: '清空已保存的敏感配置？',
    content: '清空后无法恢复，如需继续使用必须重新填写。',
    okText: '清空',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => clearSensitiveField(key),
  })
}

const saveTaskConfig = async () => {
  if (isInitializing.value || !userId.value) return
  const updateResult: unknown = await api.updateUser(scriptId, userId.value, {
    Task: {
      TaskIndex: formData.Task.TaskIndex,
    },
  })
  if (updateResult === false) {
    throw new Error('任务配置保存失败，请检查后端连接')
  }
}

const handleTaskIndexChange = async (value: number) => {
  formData.Task.TaskIndex = value
  saveError.value = ''
  try {
    await saveTaskConfig()
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    saveError.value = msg
    logger.error(msg)
    message.error(msg)
  }
}

const loadScriptInfo = async () => {
  const scripts = await api.getScripts(scriptId)
  const script = scripts[0]
  if (script) {
    scriptName.value = script.name
  }
  return script
}

/** ok-ww 程序不可用时禁止新建用户与进入配置编辑（无法动态读取配置字段与翻译）。 */
const validateOkwwProgram = async (): Promise<boolean> => {
  const script = await loadScriptInfo()
  const rootPath = String((script?.config as Record<string, any>)?.Info?.RootPath || '')
    .trim()
    .replace(/\\/g, '/')
  if (!rootPath || rootPath === '.') return false
  return window.electronAPI.fileExists(`${rootPath}/ok-ww.exe`)
}

/** 从后端动态注册表刷新任务序号下拉；失败则保留静态兜底。 */
const loadTaskOptions = async () => {
  try {
    const resp = await okwwConfigApi.listConfigFiles(scriptId, userId.value)
    if (resp?.code !== 200 || !Array.isArray(resp.data)) return
    const options = resp.data
      .filter(config => typeof config.taskIndex === 'number')
      .map(config => ({
        value: config.taskIndex as number,
        label: `${config.taskIndex} - ${config.displayName || config.filename}`,
      }))
      .sort((left, right) => left.value - right.value)
    if (options.length > 0) {
      okwwTaskOptions.value = options
    }
  } catch (e) {
    logger.error(`加载任务列表失败: ${e instanceof Error ? e.message : String(e)}`)
  }
}

const loadUser = async () => {
  pageLoading.value = true
  try {
    if (!userId.value) {
      await createUserImmediately()
    }
    await loadTaskOptions()
    const users = await api.getUsers(scriptId, userId.value)
    const user = users[0]
    if (!user) {
      throw new Error('用户不存在或加载失败')
    }

    const userData = user.config as Partial<OkwwUserFormData>
    passwordConfigured.value = Boolean(userData.Info?.Password)
    serverChanKeyConfigured.value = Boolean(userData.Notify?.ServerChanKey)
    const info = { ...getDefaultUserData().Info, ...(userData.Info || {}), Password: '' }
    const notify = {
      ...getDefaultUserData().Notify,
      ...(userData.Notify || {}),
      ServerChanKey: '',
    }

    Object.assign(formData, {
      Info: info,
      Task: { ...getDefaultUserData().Task, ...(userData.Task || {}) },
      Notify: notify,
      Data: { ...getDefaultUserData().Data, ...(userData.Data || {}) },
    })
    formData.Info.Mode = '详细'
    const taskIndex = Number(formData.Task.TaskIndex)
    const validIndexes = okwwTaskOptions.value.map(opt => opt.value)
    let shouldPersistTaskIndex = false
    if (!Number.isFinite(taskIndex) || !validIndexes.includes(taskIndex)) {
      formData.Task.TaskIndex = validIndexes[0] ?? 1
      shouldPersistTaskIndex = true
    }
    const patch: Record<string, any> = {}
    if (shouldPersistTaskIndex) {
      patch.Task = {
        TaskIndex: formData.Task.TaskIndex,
      }
    }
    if (Object.keys(patch).length > 0) {
      const updateResult: unknown = await api.updateUser(scriptId, userId.value, patch)
      if (updateResult === false) {
        throw new Error('任务配置自动修正失败')
      }
    }
    await nextTick()
    formData.userName = formData.Info.Name || ''
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    logger.error(msg)
    message.error('加载用户失败')
    handleCancel()
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}
const handleConfigSaved = () => {
  logger.info('OK-WW 配置已保存')
}

const goBackToScriptEdit = () => router.replace(`/scripts/${scriptId}/edit/okww`)

onMounted(async () => {
  if (!(await validateOkwwProgram())) {
    message.error(
      isEdit.value
        ? '当前 ok-ww 程序不可用，请先在脚本设置中选择正确的 ok-ww 根目录'
        : '请先在脚本设置中选择 ok-ww 根目录，再添加用户'
    )
    goBackToScriptEdit()
    return
  }
  await loadUser()
})
</script>

<style scoped>
.user-edit-container {
  min-height: 100%;
}

.cancel-button {
  border-radius: var(--v6-radius-control);
}

.user-edit-content {
  width: min(100%, 1280px);
  margin: 0 auto;
  padding: 0 var(--v6-content-padding-inline) var(--v6-space-8);
}

.config-surface {
  padding: var(--v6-space-5);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: var(--v6-vibrancy-material);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
}

.form-section {
  margin: 0;
  padding: var(--v6-space-5) 0;
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.config-form:first-of-type .form-section {
  padding-top: 0;
}

.section-header {
  margin-bottom: var(--v6-space-4);
  padding-bottom: var(--v6-space-2);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.section-header h3 {
  margin: 0;
  font-size: var(--v6-font-size-lg);
  font-weight: var(--v6-font-weight-semibold);
  display: flex;
  align-items: center;
  color: var(--v6-color-text);
}

.form-label {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  font-weight: var(--v6-font-weight-medium);
}

.help-icon {
  color: var(--v6-color-text-tertiary);
  cursor: help;
}

.modern-select {
  width: 100%;
}

.editor-section {
  padding: var(--v6-space-5) 0;
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.save-error {
  margin-bottom: var(--v6-space-4);
  border-radius: var(--v6-radius-control);
}

.config-form:last-child .form-section {
  padding-bottom: 0;
  border-bottom: 0;
}

:root[data-perf-mode='low'] .config-surface {
  background: var(--v6-color-surface);
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

@media (max-width: 768px) {
  .user-edit-content {
    padding-inline: var(--v6-space-4);
  }

  .config-surface {
    padding: var(--v6-space-4);
  }

  .config-form :deep(.ant-col) {
    flex: 0 0 100%;
    max-width: 100%;
  }
}
</style>
