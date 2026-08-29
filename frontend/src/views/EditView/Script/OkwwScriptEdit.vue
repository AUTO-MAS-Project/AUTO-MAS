<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="@/assets/ok-ww.ico" alt="ok-ww" class="breadcrumb-logo" />
            编辑脚本
          </div>
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

  <div class="script-edit-content">
    <a-card title="ok-ww 脚本配置" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="blue" class="type-tag">ok-ww</a-tag>
      </template>

      <a-form :model="formData" :rules="rules" layout="vertical" class="config-form">
        <div class="form-section">
          <div class="section-header">
            <h3>基本信息</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <span class="form-label">
                    脚本名称
                    <a-tooltip title="用于区分不同的 ok-ww 脚本实例">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="formData.name"
                  placeholder="请输入脚本名称"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('Info', 'Name', formData.name)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item name="path" :rules="rules.path">
                <template #label>
                  <span class="form-label">
                    ok-ww 路径
                    <a-tooltip title="选择 ok-ww.exe 所在目录">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    placeholder="请选择 ok-ww.exe 所在目录"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button
                    type="primary"
                    size="large"
                    class="auto-import-button"
                    :loading="isDiscoveringOkww"
                    :disabled="isSaving"
                    @click="discoverRootPath"
                  >
                    <template #icon>
                      <ImportOutlined />
                    </template>
                    一键导入
                  </a-button>
                  <a-button
                    size="large"
                    class="path-button"
                    :disabled="isDiscoveringOkww || isSaving"
                    @click="selectRootPath"
                  >
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择目录
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>游戏配置</h3>
          </div>
          <a-row :gutter="24" class="game-control-row">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="开启后由 MAS 接管游戏启停">
                    <span class="form-label">
                      启用游戏配置
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="okwwConfig.Game.Enabled"
                  size="large"
                  class="modern-input"
                  @change="handleChange('Game', 'Enabled', $event)"
                >
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="开启后，游戏启动成功后在运行 ok-ww 前按用户手机号后 4 位强制切换登录账号；用户未填写账号则不切换">
                    <span class="form-label">
                      运行前强制切换账号
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="okwwConfig.Game.AccountSwitch"
                  size="large"
                  class="modern-input"
                  :disabled="!okwwConfig.Game.Enabled"
                  @change="handleChange('Game', 'AccountSwitch', $event)"
                >
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24" class="game-control-row">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="开启后，代理启动游戏前由 MAS 检查官方版本并自行完成更新；关闭则直接启动游戏"
                  >
                    <span class="form-label">
                      启动前自动更新
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="okwwConfig.Game.IfAutoUpdate"
                  size="large"
                  class="modern-input"
                  :disabled="!okwwConfig.Game.Enabled"
                  @change="handleChange('Game', 'IfAutoUpdate', $event)"
                >
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="版本跨越较大时需整文件同步，超过该体积不再自动下载，改为中止并提示手动处理"
                  >
                    <span class="form-label">
                      整文件同步上限（GB）
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="okwwConfig.Game.UpdateFullSyncLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  :disabled="!okwwConfig.Game.Enabled"
                  @blur="
                    handleChange('Game', 'UpdateFullSyncLimit', okwwConfig.Game.UpdateFullSyncLimit)
                  "
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24" class="game-control-row">
            <a-col :span="12">
              <a-button
                size="large"
                :disabled="
                  !okwwConfig.Game.Enabled || gamePathValidation.status !== 'valid' || isSaving
                "
                @click="handleCheckUpdate"
              >
                <template #icon>
                  <ThunderboltOutlined />
                </template>
                检查更新
              </a-button>
            </a-col>
            <a-col :span="12">
              <span class="label-hint">
                由 MAS 检查官方版本并完成更新；更新前请确保游戏未在运行
              </span>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    游戏启动器
                    <span class="label-hint">仅支持鸣潮官方启动器</span>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="okwwConfig.Game.Path"
                    placeholder="请选择启动器所在目录"
                    size="large"
                    class="path-input"
                    readonly
                    :disabled="!okwwConfig.Game.Enabled"
                  />
                  <a-button
                    type="primary"
                    size="large"
                    class="auto-import-button"
                    :loading="isDiscoveringGame"
                    :disabled="!okwwConfig.Game.Enabled || isSaving"
                    @click="discoverGamePath"
                  >
                    <template #icon>
                      <ImportOutlined />
                    </template>
                    一键导入
                  </a-button>
                  <a-button
                    size="large"
                    class="path-button"
                    :disabled="!okwwConfig.Game.Enabled || isDiscoveringGame || isSaving"
                    @click="selectGameRootPath"
                  >
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择目录
                  </a-button>
                </a-input-group>
                <a-alert
                  v-if="gamePathValidation.status !== 'unknown'"
                  :type="gamePathValidation.status === 'valid' ? 'success' : 'error'"
                  :message="gamePathValidation.message"
                  show-icon
                  class="path-validation-alert"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    启动参数
                    <a-tooltip title="游戏启动参数（非 ok-ww 启动参数）">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="okwwConfig.Game.Arguments"
                  placeholder="请输入游戏启动参数"
                  size="large"
                  class="modern-input"
                  :disabled="!okwwConfig.Game.Enabled"
                  @blur="handleChange('Game', 'Arguments', okwwConfig.Game.Arguments)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    启动等待时间
                    <a-tooltip title="拉起游戏后的等待时间（秒）">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="okwwConfig.Game.WaitTime"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  :disabled="!okwwConfig.Game.Enabled"
                  @blur="handleChange('Game', 'WaitTime', okwwConfig.Game.WaitTime)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>运行配置</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    单日代理次数上限
                    <a-tooltip title="阈值为 0 时表示不限制">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="okwwConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', okwwConfig.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    重试次数限制
                    <a-tooltip title="超过该次数仍失败则终止">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="okwwConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', okwwConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    代理超时限制（分钟）
                    <a-tooltip title="日志长期无变化将判定超时">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="okwwConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', okwwConfig.Run.RunTimeLimit)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>
      </a-form>
    </a-card>
  </div>

  <a-modal
    v-model:open="updateModal.open"
    :title="updateModal.running ? '鸣潮更新进度' : '检查鸣潮更新'"
    :confirm-loading="updateModal.starting"
    :mask-closable="!updateModal.running"
    :footer="updateModal.running ? null : undefined"
    @ok="startUpdate"
    @cancel="handleUpdateModalCancel"
  >
    <template v-if="!updateModal.running">
      <a-form layout="vertical">
        <a-form-item label="选择用户（按该用户的服务器检查更新）">
          <a-select v-model:value="updateModal.selectedUserId" style="width: 100%">
            <a-select-option v-for="user in updateModal.users" :key="user.uid" :value="user.uid">
              {{ user.name }}（{{ user.resource }}）
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-alert
          type="info"
          show-icon
          message="将按所选服务器检查并更新鸣潮，更新过程可能下载数 GB 数据，请确保游戏未在运行"
        />
      </a-form>
    </template>
    <template v-else>
      <div class="update-log-area">
        <pre class="update-log-content">{{ updateModal.log || '正在连接更新任务...' }}</pre>
      </div>
    </template>
  </a-modal>

  <a-modal
    v-model:open="candidateModal.open"
    title="选择导入路径"
    :confirm-loading="candidateModal.loading"
    @ok="confirmCandidateSelection"
    @cancel="closeCandidateModal"
  >
    <a-form layout="vertical">
      <a-form-item label="检测到多个可用路径，请选择当前脚本使用的路径">
        <a-select v-model:value="candidateModal.selectedPath" style="width: 100%">
          <a-select-option
            v-for="candidate in candidateModal.candidates"
            :key="candidate.path"
            :value="candidate.path"
          >
            {{ candidateDisplayLabel(candidate) }}
          </a-select-option>
        </a-select>
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  FolderOpenOutlined,
  ImportOutlined,
  QuestionCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import { Service, TaskCreateIn } from '@/api'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_TASK_COMPLETED,
  WS_TASK_LOG_UPDATED,
  WS_TASK_NOTICE,
  type WSTaskLogUpdatedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import type { PathDiscoveryCandidate } from '@/types/electron'

const logger = window.electronAPI.getLogger('ok-ww脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()
const { getUsers } = useUserApi()
const { subscribe, unsubscribe } = useWebSocket()

const scriptId = route.params.id as string
const pageLoading = ref(true)
const isSaving = ref(false)
const isInitializing = ref(true)
const isDiscoveringOkww = ref(false)
const isDiscoveringGame = ref(false)

// ══ okww 项目结构常量（需与 app/task/Okww/AutoProxy.py 中的 _OKWW_REL_* 保持同步）══
const OKWW_EXE_NAME = 'ok-ww.exe'
const OKWW_APP_JSON_PATH = 'data/apps/ok-ww/app.json'

interface OkwwInfoForm {
  Name: string
  RootPath: string
}

interface OkwwGameForm {
  Enabled: boolean
  AccountSwitch: boolean
  Path: string
  Arguments: string
  WaitTime: number
  IfAutoUpdate: boolean
  UpdateFullSyncLimit: number
}

interface OkwwRunForm {
  ProxyTimesLimit: number
  RunTimesLimit: number
  RunTimeLimit: number
}

interface OkwwScriptConfigForm {
  Info: OkwwInfoForm
  Script: Record<string, never>
  Game: OkwwGameForm
  Run: OkwwRunForm
}

const formData = reactive({
  name: '',
  get path() {
    return okwwConfig.Info.RootPath
  },
  set path(value: string) {
    okwwConfig.Info.RootPath = value
  },
})

const okwwConfig = reactive<OkwwScriptConfigForm>({
  Info: { Name: '', RootPath: '.' },
  Script: {},
  Game: {
    Enabled: false,
    AccountSwitch: false,
    Path: '.',
    Arguments: '',
    WaitTime: 60,
    IfAutoUpdate: true,
    UpdateFullSyncLimit: 30,
  },
  Run: { ProxyTimesLimit: 0, RunTimesLimit: 3, RunTimeLimit: 60 },
})

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  path: [{ required: true, message: '请选择 ok-ww 路径', trigger: 'blur' }],
}

const WUWA_LAUNCHER_EXECUTABLE = 'launcher.exe'

type DiscoveryKind = 'okww' | 'game'
type PathValidationStatus = 'unknown' | 'valid' | 'invalid'

const candidateModal = reactive({
  open: false,
  kind: null as DiscoveryKind | null,
  selectedPath: '',
  candidates: [] as PathDiscoveryCandidate[],
  loading: false,
})

const gamePathValidation = reactive({
  status: 'unknown' as PathValidationStatus,
  message: '',
})

interface UpdateUserOption {
  uid: string
  name: string
  resource: string
}

const updateModal = reactive({
  open: false,
  running: false,
  starting: false,
  users: [] as UpdateUserOption[],
  selectedUserId: '',
  log: '',
})

const updateSession = reactive({
  subscriptionIds: [] as string[],
  taskId: '',
  timeout: null as number | null,
})

const clearUpdateSession = () => {
  for (const subscriptionId of updateSession.subscriptionIds) {
    unsubscribe(subscriptionId)
  }
  updateSession.subscriptionIds = []
  updateSession.taskId = ''
  if (updateSession.timeout) {
    window.clearTimeout(updateSession.timeout)
    updateSession.timeout = null
  }
}

const stopUpdateSession = async (): Promise<boolean> => {
  const taskId = updateSession.taskId
  if (!taskId) {
    clearUpdateSession()
    return true
  }
  try {
    const response = await Service.stopTaskApiDispatchStopPost({ taskId })
    if (response.code !== 200) {
      throw new Error(response.message || '停止鸣潮更新失败')
    }
    return true
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    return false
  } finally {
    clearUpdateSession()
  }
}

const handleCheckUpdate = async () => {
  if (updateModal.running) return
  try {
    const resp = await getUsers(scriptId)
    const data = (resp?.data || {}) as Record<string, any>
    const users: UpdateUserOption[] = Object.entries(data)
      .filter(([, user]) => user?.Info?.Status !== false)
      .map(([uid, user]) => ({
        uid,
        name: user?.Info?.Name || uid,
        resource: user?.Info?.Resource || '官服',
      }))
    if (!users.length) {
      message.warning('请先添加并启用用户，再进行更新检查')
      return
    }
    updateModal.users = users
    updateModal.selectedUserId = users[0].uid
    updateModal.log = ''
    updateModal.open = true
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error('加载用户失败')
  }
}

const startUpdate = async () => {
  if (!updateModal.selectedUserId) return
  updateModal.starting = true
  try {
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: updateModal.selectedUserId,
      mode: TaskCreateIn.mode.UPDATE,
    })
    if (response.code !== 200 || !response.taskId) {
      throw new Error(response.message || '启动鸣潮更新失败')
    }
    updateModal.running = true
    updateSession.taskId = response.taskId
    updateSession.subscriptionIds = [
      subscribe({ id: response.taskId, type: WS_TASK_LOG_UPDATED }, wsMessage => {
        const data = wsMessage.data as unknown as WSTaskLogUpdatedData
        updateModal.log = data.log
      }),
      subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
        const data = wsMessage.data as unknown as WSTaskNoticeData
        if (data.level === 'error') {
          message.error(`鸣潮更新失败: ${data.message}`)
          updateModal.running = false
          updateModal.open = false
          void stopUpdateSession()
        }
      }),
      subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
        message.success('鸣潮更新任务已结束')
        updateModal.running = false
        updateModal.open = false
        void stopUpdateSession()
      }),
    ]
    updateSession.timeout = window.setTimeout(
      () => {
        message.error('鸣潮更新超时，已自动停止')
        void stopUpdateSession()
      },
      30 * 60 * 1000
    )
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(e instanceof Error ? e.message : '启动鸣潮更新失败')
  } finally {
    updateModal.starting = false
  }
}

const handleUpdateModalCancel = () => {
  if (updateModal.running) {
    void stopUpdateSession()
  }
  updateModal.running = false
  updateModal.open = false
}

const showPathRejectModal = (title: string, content: string) => {
  Modal.error({ title, content, okText: '我知道了' })
}

const closeCandidateModal = () => {
  candidateModal.open = false
  candidateModal.kind = null
  candidateModal.selectedPath = ''
  candidateModal.candidates = []
}

const openCandidateModal = (kind: DiscoveryKind, candidates: PathDiscoveryCandidate[]) => {
  candidateModal.kind = kind
  candidateModal.candidates = candidates
  candidateModal.selectedPath = candidates[0]?.path || ''
  candidateModal.open = true
}

const handleCancel = () => router.push('/scripts')

const handleChange = async (category: string, key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value) return
  isSaving.value = true
  try {
    const updateData = { [category]: { [key]: value } } as Record<string, Record<string, unknown>>
    const success = await updateScript(scriptId, updateData)
    if (success) {
      logger.info(`配置已保存: ${category}.${key}`)
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    logger.error(msg)
  } finally {
    isSaving.value = false
  }
}

const validateGamePath = async (launcherPath: string) => {
  const normalized = launcherPath.replace(/\\/g, '/').replace(/\/+$/g, '')
  const executable = normalized.split('/').pop()?.toLowerCase()
  if (!normalized || normalized === '.' || executable !== WUWA_LAUNCHER_EXECUTABLE) {
    gamePathValidation.status = 'invalid'
    gamePathValidation.message = '当前游戏路径不合法：请选择鸣潮官方启动器 launcher.exe'
    return false
  }

  let exists = false
  try {
    exists = await window.electronAPI.fileExists(normalized)
  } catch {
    gamePathValidation.status = 'invalid'
    gamePathValidation.message = '当前游戏路径不合法：无法完成启动器文件校验'
    return false
  }
  if (!exists) {
    gamePathValidation.status = 'invalid'
    gamePathValidation.message = '当前游戏路径不合法：启动器文件不存在'
    return false
  }

  gamePathValidation.status = 'valid'
  gamePathValidation.message = `当前游戏路径合法：已找到 ${executable}`
  return true
}

const applyRootPathDefaults = async (rootPath: string, successMessage = 'ok-ww 根目录已保存') => {
  if (!rootPath || rootPath === '.') {
    message.warning('请先选择脚本根目录')
    return false
  }
  const norm = rootPath.replace(/\\/g, '/').replace(/\/+$/g, '')
  const previousPath = okwwConfig.Info.RootPath
  okwwConfig.Info.RootPath = norm

  isSaving.value = true
  try {
    const success = await updateScript(scriptId, {
      Info: { RootPath: norm },
    })
    if (success) {
      message.success(successMessage)
      return true
    }
    okwwConfig.Info.RootPath = previousPath
    return false
  } catch (error) {
    okwwConfig.Info.RootPath = previousPath
    throw error
  } finally {
    isSaving.value = false
  }
}

const saveGamePath = async (launcherPath: string, successMessage: string) => {
  const normalized = launcherPath.replace(/\\/g, '/')
  if (!(await validateGamePath(normalized))) return false
  const previousPath = okwwConfig.Game.Path
  okwwConfig.Game.Path = normalized
  isSaving.value = true
  try {
    const success = await updateScript(scriptId, {
      Game: { Path: normalized },
    })
    if (success) {
      message.success(successMessage)
      return true
    }
    okwwConfig.Game.Path = previousPath
    await validateGamePath(previousPath)
    return false
  } catch (error) {
    okwwConfig.Game.Path = previousPath
    await validateGamePath(previousPath)
    throw error
  } finally {
    isSaving.value = false
  }
}

const loadScript = async () => {
  pageLoading.value = true
  isInitializing.value = true
  try {
    const detail = await getScript(scriptId)
    if (!detail) {
      message.error('脚本不存在或加载失败')
      handleCancel()
      return
    }
    if (detail.type !== 'Okww') {
      message.error('脚本类型不是 ok-ww')
      handleCancel()
      return
    }
    formData.name = detail.name
    const config = detail.config as Partial<OkwwScriptConfigForm>
    Object.assign(okwwConfig.Info, config.Info || {})
    Object.assign(okwwConfig.Script, config.Script || {})
    Object.assign(okwwConfig.Game, config.Game || {})
    Object.assign(okwwConfig.Run, config.Run || {})
    if (okwwConfig.Game.Path && okwwConfig.Game.Path !== '.') {
      await validateGamePath(okwwConfig.Game.Path)
    }
  } catch {
    message.error('加载脚本失败')
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const selectRootPath = async () => {
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return
  const normalized = picked.replace(/\\/g, '/')
  const sentinelPaths = [OKWW_EXE_NAME, OKWW_APP_JSON_PATH]
  const exists = await Promise.all(
    sentinelPaths.map(relativePath =>
      window.electronAPI.fileExists(`${normalized}/${relativePath}`)
    )
  )
  const missingPath = sentinelPaths.find((_, index) => !exists[index])
  if (missingPath) {
    showPathRejectModal(
      '所选目录无效',
      `所选目录下未找到 ${missingPath}，请选择完整的 OK-WW 脚本根目录。`
    )
    return
  }
  formData.path = normalized
  await applyRootPathDefaults(normalized)
}

const discoverRootPath = async () => {
  if (isDiscoveringOkww.value) return
  isDiscoveringOkww.value = true
  try {
    const result = await window.electronAPI.discoverOkwwPath()
    const candidates = result.candidates || (result.path ? [{ path: result.path }] : [])
    if (!result.success || candidates.length === 0) {
      showPathRejectModal('未找到 ok-ww', result.error || '未找到有效的 ok-ww 安装目录')
      return
    }
    if (candidates.length > 1) {
      openCandidateModal('okww', candidates)
      return
    }
    await applyRootPathDefaults(candidates[0].path, '已从卸载信息导入 ok-ww 路径')
  } catch (error) {
    logger.error(`一键导入 ok-ww 路径失败: ${error instanceof Error ? error.message : error}`)
    showPathRejectModal('导入失败', '读取 ok-ww 安装信息时发生错误，请使用“选择目录”手动导入')
  } finally {
    isDiscoveringOkww.value = false
  }
}

const gameSourceLabel = (channel?: PathDiscoveryCandidate['channel']) => {
  if (channel === 'China') return '官方启动器（国服）'
  if (channel === 'Global') return '官方启动器（Global）'
  return '官方启动器'
}

const candidateDisplayLabel = (candidate: PathDiscoveryCandidate) => {
  const channel = candidate.channel ? `（${gameSourceLabel(candidate.channel)}）` : ''
  return `${candidate.path}${channel}`
}

const discoverGamePath = async () => {
  if (!okwwConfig.Game.Enabled || isDiscoveringGame.value) return
  isDiscoveringGame.value = true
  try {
    const result = await window.electronAPI.discoverWutheringWavesPath()
    const candidates =
      result.candidates || (result.path ? [{ path: result.path, channel: result.channel }] : [])
    if (!result.success || candidates.length === 0) {
      showPathRejectModal('未找到鸣潮', result.error || '未找到有效的鸣潮启动器')
      return
    }
    if (candidates.length > 1) {
      openCandidateModal('game', candidates)
      return
    }
    const [candidate] = candidates
    await saveGamePath(candidate.path, `已从${gameSourceLabel(candidate.channel)}导入鸣潮启动器`)
  } catch (error) {
    logger.error(`一键导入鸣潮路径失败: ${error instanceof Error ? error.message : error}`)
    showPathRejectModal('导入失败', '读取鸣潮启动器信息时发生错误，请使用“选择目录”手动导入')
  } finally {
    isDiscoveringGame.value = false
  }
}

const confirmCandidateSelection = async () => {
  const selected = candidateModal.candidates.find(
    candidate => candidate.path === candidateModal.selectedPath
  )
  if (!selected || !candidateModal.kind) return

  candidateModal.loading = true
  try {
    const success =
      candidateModal.kind === 'okww'
        ? await applyRootPathDefaults(selected.path, '已导入所选 ok-ww 路径')
        : await saveGamePath(
            selected.path,
            `已从${gameSourceLabel(selected.channel)}导入鸣潮启动器`
          )
    if (success) closeCandidateModal()
  } catch (error) {
    logger.error(`保存所选路径失败: ${error instanceof Error ? error.message : error}`)
  } finally {
    candidateModal.loading = false
  }
}

const selectGameRootPath = async () => {
  if (!okwwConfig.Game.Enabled) return
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return

  const normalized = picked.replace(/\\/g, '/')

  const candidateExe = normalized + '/' + WUWA_LAUNCHER_EXECUTABLE
  if (await window.electronAPI.fileExists(candidateExe)) {
    await saveGamePath(candidateExe, '鸣潮启动器路径已保存')
    return
  }

  showPathRejectModal(
    '所选目录无效',
    '所选目录下未找到 launcher.exe，请选择鸣潮官方启动器的安装目录。'
  )
}

onMounted(loadScript)

onUnmounted(() => {
  void stopUpdateSession()
})
</script>

<style scoped>
.script-edit-header {
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
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  text-decoration: none;
}

.breadcrumb-current {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text);
  font-weight: 600;
}

.breadcrumb-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.script-edit-content {
  flex: 1;
}

.config-card {
  overflow: hidden;
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
  padding: 24px 32px;
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
}

.form-section {
  margin-bottom: 12px;
}

.section-header {
  margin-bottom: 6px;
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

.label-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--ant-color-text-tertiary);
}

.label-hint strong {
  font-weight: 600;
  color: var(--ant-color-text-secondary);
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

.path-input-group {
  display: flex;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  min-width: 0;
  border: none !important;
  border-radius: 0 !important;
}

.auto-import-button {
  flex-shrink: 0;
  border-radius: 0;
  padding: 0 18px;
}

.path-button {
  flex-shrink: 0;
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.path-validation-alert {
  margin-top: 8px;
}

.update-log-area {
  max-height: 320px;
  overflow-y: auto;
  padding: 12px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-layout);
}

.update-log-content {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--ant-color-text);
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 24px;
}

.game-control-row {
  margin-bottom: 8px;
}

.game-control-row :deep(.ant-form-item) {
  margin-bottom: 0;
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }
}
</style>
