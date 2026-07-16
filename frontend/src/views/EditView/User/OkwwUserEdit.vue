<template>
  <div class="user-edit-container">
    <div class="user-edit-header">
      <div class="header-nav">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts">脚本管理</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <router-link :to="`/scripts/${scriptId}/edit/okww`" class="breadcrumb-link">
              {{ scriptName }}
            </router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            {{ isEdit ? '编辑用户' : '添加用户' }}
          </a-breadcrumb-item>
        </a-breadcrumb>
      </div>

      <a-space size="middle">
        <a-button size="large" class="cancel-button" @click="handleCancel">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          返回
        </a-button>
      </a-space>
    </div>

    <div class="user-edit-content">
      <a-card class="config-card" :loading="pageLoading">
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
                      <a-tooltip title="用于区分用户的名称，相同名称的用户将被视为同一用户进行统计">
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
                  <a-input-password
                    v-model:value="formData.Info.Password"
                    placeholder="请输入密码"
                    size="large"
                    class="modern-input"
                    @blur="saveField('Info.Password', formData.Info.Password)"
                  />
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
      </a-card>

      <!-- OK-WW 配置编辑器 -->
      <a-card class="config-card" style="margin-top: 24px">
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

        <OkScriptConfigEditor
          v-if="userId"
          :script-id="scriptId"
          :user-id="userId"
          endpoint-prefix="/plugin/okww/configs"
          @saved="handleConfigSaved"
          @unavailable="goBackToScriptEdit"
        />
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <ExtraScriptSection :form-data="formData" :loading="pageLoading" @save="saveField" />
        </a-form>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
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
                <a-input
                  v-model:value="formData.Notify.ServerChanKey"
                  placeholder="请输入 SENDKEY"
                  :disabled="!formData.Notify.Enabled || !formData.Notify.IfServerChan"
                  size="large"
                  @blur="saveField('Notify.ServerChanKey', formData.Notify.ServerChanKey)"
                />
              </a-col>
            </a-row>

            <div style="margin-top: 16px">
              <WebhookManager mode="user" :script-id="scriptId" :user-id="userId" />
            </div>
          </div>
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
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

  isSaving.value = true
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

    await api.updateUser(scriptId, userId.value, patch)
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    logger.error(msg)
    message.error(msg)
  } finally {
    isSaving.value = false
  }
}

const saveTaskConfig = async () => {
  if (isInitializing.value || !userId.value) return
  await api.updateUser(scriptId, userId.value, {
    Task: {
      TaskIndex: formData.Task.TaskIndex,
    },
  })
}

const handleTaskIndexChange = async (value: number) => {
  formData.Task.TaskIndex = value
  try {
    await saveTaskConfig()
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
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

    Object.assign(formData, {
      Info: { ...getDefaultUserData().Info, ...(userData.Info || {}) },
      Task: { ...getDefaultUserData().Task, ...(userData.Task || {}) },
      Notify: { ...getDefaultUserData().Notify, ...(userData.Notify || {}) },
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
      await api.updateUser(scriptId, userId.value, patch)
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
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

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

.cancel-button {
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
}

.user-edit-content {
  max-width: 1200px;
  margin: 0 auto;
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

.modern-select {
  width: 100%;
}

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .user-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }
}
</style>
