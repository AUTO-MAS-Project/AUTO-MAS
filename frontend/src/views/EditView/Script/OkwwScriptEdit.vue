<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="@/assets/ok-ww.ico" alt="ok-ww" class="breadcrumb-logo" />
            {{ t('edit.editScript') }}
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <DocLink :url="MAS_DOC_URLS.scriptTypes.Okww" />
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        {{ t('edit.back') }}
      </a-button>
    </a-space>
  </div>

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
    <a-card :title="t('edit.okWwScriptConfiguration')" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="blue" class="type-tag">ok-ww</a-tag>
      </template>

      <a-form :model="formData" :rules="rules" layout="vertical" class="config-form">
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.basicInfo') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <span class="form-label">
                    {{ t('edit.scriptName') }}
                    <a-tooltip :title="t('edit.tellsOkWwScript')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="formData.name"
                  :placeholder="t('edit.enterScriptName')"
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
                    {{ t('edit.okWwPath') }}
                    <a-tooltip :title="t('edit.pickDirectoryHoldingOk4')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    :placeholder="t('edit.pickDirectoryHoldingOk2')"
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
                    {{ t('edit.import') }}
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
                    {{ t('edit.pickDirectory') }}
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.gameConfiguration') }}</h3>
          </div>
          <a-row :gutter="24" class="game-control-row">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.masTakesOverStarting')">
                    <span class="form-label">
                      {{ t('edit.enableGameConfiguration') }}
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
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.okwwAccountSwitchHint')">
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
                <span class="control-hint">
                  {{ t('edit.accountSwitch16x9ArgHint', { p0: '-Res=1920x1080' }) }}
                </span>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24" class="game-control-row">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.beforeLaunchingGameRun')">
                    <span class="form-label">
                      {{ t('edit.updateAutomaticallyBeforeLaunching') }}
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
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
                <span
                  v-if="
                    okwwConfig.Game.Type === 'Client' &&
                    (!okwwConfig.Game.Path || okwwConfig.Game.Path === '.')
                  "
                  class="control-hint"
                >
                  {{ t('edit.autoUpdateNeedsLauncher') }}
                </span>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.largeVersionGapNeeds')">
                    <span class="form-label">
                      {{ t('edit.wholeFileSyncLimit') }}
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
                {{ t('edit.checkUpdates') }}
              </a-button>
            </a-col>
            <a-col :span="12">
              <span class="label-hint">
                {{ t('edit.masChecksOfficialVersion') }}
              </span>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <div class="launch-type-label">
                    <span class="form-label">
                      {{ t('edit.launchType') }}
                      <a-tooltip :title="t('edit.launchTypeHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                    <a-radio-group
                      v-model:value="okwwConfig.Game.Type"
                      class="launch-type-toggle"
                      size="small"
                      button-style="solid"
                      :disabled="!okwwConfig.Game.Enabled"
                    >
                      <a-radio-button value="Client">
                        {{ t('edit.launchDirectly') }}
                      </a-radio-button>
                      <a-radio-button value="Launcher">
                        {{ t('edit.launchViaLauncher') }}
                      </a-radio-button>
                    </a-radio-group>
                  </div>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="okwwConfig.Game.Path"
                    :placeholder="t('edit.pickLauncherDirectory')"
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
                    {{ t('edit.import') }}
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
                    {{ t('edit.pickDirectory') }}
                  </a-button>
                </a-input-group>
                <a-alert
                  v-if="gamePathValidation.status !== 'unknown'"
                  :type="gamePathValidation.status === 'valid' ? 'success' : 'error'"
                  :message="gamePathValidation.message"
                  show-icon
                  class="path-validation-alert"
                />
                <div v-if="okwwConfig.Game.Type === 'Client'" class="derived-client-row">
                  <span class="label-hint">{{ t('edit.gameClientPathLabel') }}</span>
                  <a-input-group compact class="path-input-group">
                    <a-input
                      :value="okwwConfig.Game.ClientPath || derivedClientPath"
                      :placeholder="t('edit.clientPathPending')"
                      size="large"
                      class="path-input"
                      readonly
                      :disabled="!okwwConfig.Game.Enabled"
                    />
                    <a-button
                      size="large"
                      class="path-button"
                      :disabled="!okwwConfig.Game.Enabled || isSaving"
                      @click="selectClientPath"
                    >
                      <template #icon>
                        <FolderOpenOutlined />
                      </template>
                      {{ t('edit.selectFile') }}
                    </a-button>
                    <a-button
                      v-if="okwwConfig.Game.ClientPath"
                      size="large"
                      class="path-button"
                      :disabled="!okwwConfig.Game.Enabled || isSaving"
                      @click="resetClientPath"
                    >
                      {{ t('edit.resetAutoLocate') }}
                    </a-button>
                  </a-input-group>
                </div>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.launchArguments') }}
                    <a-tooltip :title="t('edit.gameLaunchArgumentsNot2')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="okwwConfig.Game.Arguments"
                  :placeholder="t('edit.enterGameLaunchArguments')"
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
                    {{ t('edit.startupWait') }}
                    <a-tooltip :title="t('edit.howLongWaitAfter')">
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
            <h3>{{ t('edit.runConfiguration') }}</h3>
          </div>
          <ScriptHardTimeoutField
            v-model:value="okwwConfig.Run.HardTimeLimit"
            @save="handleChange('Run', 'HardTimeLimit', okwwConfig.Run.HardTimeLimit)"
          />
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runsPerDay') }}
                    <a-tooltip :title="t('edit.k0MeansNoLimit')">
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
                    {{ t('edit.retryLimit2') }}
                    <a-tooltip :title="t('edit.giveUpAfterThis')">
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
                    {{ t('edit.runTimeoutMinutes') }}
                    <a-tooltip :title="t('edit.logThatStaysUnchanged')">
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
  </ConfigLockPanel>

  <a-modal
    v-model:open="updateModal.open"
    :title="updateModal.running ? t('edit.okwwUpdateProgress') : t('edit.okwwCheckUpdateTitle')"
    :confirm-loading="updateModal.starting"
    :mask-closable="!updateModal.running"
    :footer="updateModal.running ? null : undefined"
    @ok="startUpdate"
    @cancel="handleUpdateModalCancel"
  >
    <template v-if="!updateModal.running">
      <a-form layout="vertical">
        <a-form-item :label="t('edit.pickUserWhoseServer')">
          <a-select v-model:value="updateModal.selectedUserId" style="width: 100%">
            <a-select-option v-for="user in updateModal.users" :key="user.uid" :value="user.uid">
              {{ user.name }}（{{ user.resource }}）
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-alert type="info" show-icon :message="t('edit.wutheringWavesWillBe')" />
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
    :title="t('edit.pickImportPath')"
    :confirm-loading="candidateModal.loading"
    @ok="confirmCandidateSelection"
    @cancel="closeCandidateModal"
  >
    <a-form layout="vertical">
      <a-form-item :label="t('edit.severalUsablePathsWere')">
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
import ScriptHardTimeoutField from '@/views/EditView/Script/components/ScriptHardTimeoutField.vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import DocLink from '@/components/DocLink.vue'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { useI18n } from 'vue-i18n'
import { onMounted, onUnmounted, reactive, ref, watch } from 'vue'
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
import { useSaveQueue } from '@/composables/useSaveQueue'
import { useUserApi } from '@/composables/useUserApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { realtimeSnapshotApi } from '@/services/realtimeSnapshotApi'
import {
  WS_TASK_COMPLETED,
  WS_TASK_LOG_UPDATED,
  WS_TASK_NOTICE,
  type WSTaskLogUpdatedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import type { PathDiscoveryCandidate } from '@/types/electron'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('ok-ww脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()
const { getUsers } = useUserApi()
const { subscribe, unsubscribe } = useWebSocket()

const scriptId = route.params.id as string
const pageLoading = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { isSaving, enqueue } = useSaveQueue()
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
  Type: 'Launcher' | 'Client'
  Path: string
  ClientPath: string
  Arguments: string
  WaitTime: number
  IfAutoUpdate: boolean
  UpdateFullSyncLimit: number
}

interface OkwwRunForm {
  HardTimeLimit: number
  ProxyTimesLimit: number
  RunTimesLimit: number
  RunTimeLimit: number
}

interface OkwwScriptConfigForm {
  Info: OkwwInfoForm
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
  Game: {
    Enabled: false,
    AccountSwitch: false,
    Type: 'Client',
    Path: '.',
    ClientPath: '',
    Arguments: '',
    WaitTime: 60,
    IfAutoUpdate: true,
    UpdateFullSyncLimit: 30,
  },
  Run: { HardTimeLimit: 120, ProxyTimesLimit: 0, RunTimesLimit: 3, RunTimeLimit: 60 },
})

const rules = {
  name: [{ required: true, message: t('edit.enterScriptName'), trigger: 'blur' }],
  path: [{ required: true, message: t('edit.pickOkWwPath'), trigger: 'blur' }],
}

const WUWA_LAUNCHER_EXECUTABLE = 'launcher.exe'
// 直启客户端的进程名，与 app/task/Okww/AutoProxy.py 的 _WUWA_CLIENT_PROCESS 逐字一致
// （后端按进程名精确匹配，大小写不同会被拒绝）
const WUWA_CLIENT_EXECUTABLE = 'Client-Win64-Shipping.exe'

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

// 直启模式下展示的客户端 exe 路径（由后端解码启动器得到，仅展示不落盘）
const derivedClientPath = ref('')

// 已持久化的启动方式：保存失败时回滚到它
let persistedLaunchType: 'Launcher' | 'Client' | null = null
// 最近一次主动发起/接受的目标值：抑制回滚恢复与重复赋值触发的重复提交
let requestedLaunchType: 'Launcher' | 'Client' | null = null

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
      message.warning(t('edit.addEnableUserBefore'))
      return
    }
    updateModal.users = users
    updateModal.selectedUserId = users[0].uid
    updateModal.log = ''
    updateLogSeq = null
    updateModal.open = true
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(t('edit.couldNotLoadUser'))
  }
}

// 任务日志增量协议：append 为假 → 整体替换并记 seq；append 为真且 seq 连续 → 追加；
// 否则视为失步（订阅登记前已经错过首条整体替换、或漏了消息）：丢弃本条，拉一次运行
// 快照用它的 log/logSeq 重建，重建期间到达的增量一并丢弃。缓冲上限 200,000 字符。
const UPDATE_LOG_MAX_CHARS = 200_000
let updateLogSeq: number | null = null
let updateLogResyncing = false
const resyncUpdateLog = async () => {
  if (updateLogResyncing || !updateSession.taskId) return
  updateLogResyncing = true
  try {
    const snapshot = await realtimeSnapshotApi.getRuntimeTasks()
    const item = (snapshot.tasks ?? []).find(task => task.taskId === updateSession.taskId)
    if (!item) return
    updateModal.log = item.log ?? ''
    updateLogSeq = item.logSeq ?? null
  } catch (e) {
    logger.warn(`重建鸣潮更新日志失败: ${e instanceof Error ? e.message : String(e)}`)
  } finally {
    updateLogResyncing = false
  }
}
const applyUpdateLog = (data: { log: string; seq?: number; append?: boolean }) => {
  if (!data.append) {
    updateModal.log = data.log
    updateLogSeq = data.seq ?? null
  } else if (updateLogSeq !== null && data.seq === updateLogSeq + 1) {
    updateModal.log += data.log
    updateLogSeq = data.seq
  } else {
    updateLogSeq = null
    void resyncUpdateLog()
    return
  }
  if (updateModal.log.length > UPDATE_LOG_MAX_CHARS) {
    updateModal.log = updateModal.log.slice(-UPDATE_LOG_MAX_CHARS)
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
        applyUpdateLog(
          wsMessage.data as unknown as WSTaskLogUpdatedData & { seq?: number; append?: boolean }
        )
      }),
      subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
        const data = wsMessage.data as unknown as WSTaskNoticeData
        if (data.level === 'error') {
          message.error(t('edit.wutheringWavesUpdateFailed', { p0: data.message }))
          updateModal.running = false
          updateModal.open = false
          void stopUpdateSession()
        }
      }),
      subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
        message.success(t('edit.wutheringWavesUpdateTask'))
        updateModal.running = false
        updateModal.open = false
        void stopUpdateSession()
      }),
    ]
    updateSession.timeout = window.setTimeout(
      () => {
        message.error(t('edit.wutheringWavesUpdateTimed'))
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
  Modal.error({ title, content, okText: t('edit.gotIt') })
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
  if (isInitializing.value) return
  await enqueue(async () => {
    try {
      const updateData = { [category]: { [key]: value } } as Record<string, Record<string, unknown>>
      const success = await updateScript(scriptId, updateData)
      if (success) {
        logger.info(`配置已保存: ${category}.${key}`)
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      logger.error(msg)
    }
  }, `${category}.${key}`)
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
    message.warning(t('edit.pickScriptRootDirectory'))
    return false
  }
  const norm = rootPath.replace(/\\/g, '/').replace(/\/+$/g, '')
  const previousPath = okwwConfig.Info.RootPath
  okwwConfig.Info.RootPath = norm

  return enqueue(async () => {
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
    }
  })
}

const saveGamePath = async (launcherPath: string, successMessage: string) => {
  const normalized = launcherPath.replace(/\\/g, '/')
  if (!(await validateGamePath(normalized))) return false
  const previousPath = okwwConfig.Game.Path
  okwwConfig.Game.Path = normalized
  const success = await enqueue(async () => {
    try {
      const ok = await updateScript(scriptId, {
        Game: { Path: normalized },
      })
      if (ok) {
        message.success(successMessage)
      } else {
        okwwConfig.Game.Path = previousPath
        await validateGamePath(previousPath)
      }
      return ok
    } catch (error) {
      okwwConfig.Game.Path = previousPath
      await validateGamePath(previousPath)
      throw error
    }
  })
  if (success && okwwConfig.Game.Type === 'Client') {
    // 启动器路径变了，直启模式的客户端路径展示需要重新解码
    await refreshDerivedClientPath()
  }
  return success
}

const loadScript = async () => {
  pageLoading.value = true
  isInitializing.value = true
  try {
    const detail = await getScript(scriptId)
    if (!detail) {
      message.error(t('edit.scriptDoesNotExist'))
      handleCancel()
      return
    }
    if (detail.type !== 'Okww') {
      message.error(t('edit.scriptTypeNotOk2'))
      handleCancel()
      return
    }
    formData.name = detail.name
    const config = detail.config as Partial<OkwwScriptConfigForm>
    Object.assign(okwwConfig.Info, config.Info || {})
    Object.assign(okwwConfig.Game, config.Game || {})
    Object.assign(okwwConfig.Run, config.Run || {})
    if (okwwConfig.Game.Path && okwwConfig.Game.Path !== '.') {
      await validateGamePath(okwwConfig.Game.Path)
    }
    if (okwwConfig.Game.Type === 'Client') {
      await refreshDerivedClientPath()
    }
    persistedLaunchType = okwwConfig.Game.Type
    requestedLaunchType = okwwConfig.Game.Type
  } catch {
    message.error(t('edit.couldNotLoadScript'))
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

// 直启模式的客户端路径由后端解码启动器得到，仅用于前端展示；任务期真正启动的
// exe 由后端自行解码，不落盘配置。
// 已手动指定 ClientPath 时展示值不来自解码，跳过调用避免无谓的失败提示
const refreshDerivedClientPath = async () => {
  if (okwwConfig.Game.ClientPath) return
  if (!okwwConfig.Game.Path || okwwConfig.Game.Path === '.') {
    derivedClientPath.value = ''
    return
  }
  try {
    const result = await Service.getOkwwClientPathApiApiScriptsOkwwClientPathGet(scriptId)
    if (result.code === 200) {
      derivedClientPath.value = result.client_path
    } else {
      derivedClientPath.value = ''
      message.warning(t('edit.clientPathLocateFailed', { message: result.message }))
    }
  } catch (error) {
    logger.error(`解码鸣潮客户端路径失败: ${error instanceof Error ? error.message : error}`)
    derivedClientPath.value = ''
    message.warning(t('edit.clientPathLocateFailedHint'))
  }
}

// 切换启动方式：Game.Path 恒为启动器路径，两种方式都由它定位游戏，切换只
// 影响 MAS 的拉起方式，路径无需改动；直启模式刷新客户端路径展示
const handleLaunchTypeChange = async (value: 'Launcher' | 'Client') => {
  // 先更新哨兵再回滚赋值：让 watch 认定这是自己接受的目标值，不再重复提交；
  // 回滚目标读当前已持久化值而非入队快照——队列中更早的请求可能已落库
  const rollback = () => {
    if (persistedLaunchType === null) return
    requestedLaunchType = persistedLaunchType
    okwwConfig.Game.Type = persistedLaunchType
  }
  // enqueue 会把更新失败透成拒绝，这里收掉：watch 里的 void 调用漏出去会变成
  // 未处理的 promise 拒绝（失败回滚与提示已在本函数内处理）
  const success = await enqueue(async () => {
    try {
      const ok = await updateScript(scriptId, {
        Game: { Type: value },
      })
      if (!ok) rollback()
      return ok
    } catch (error) {
      rollback()
      throw error
    }
  }).catch(() => false)
  if (!success) {
    message.error(t('edit.launchTypeSaveFailed'))
    return
  }
  persistedLaunchType = value
  if (value === 'Client') {
    await refreshDerivedClientPath()
  }
}

// 手动指定直启客户端：留空（恢复自动）时由启动器路径解码定位
const saveClientPath = async (clientPath: string) => {
  const previousPath = okwwConfig.Game.ClientPath
  okwwConfig.Game.ClientPath = clientPath
  const success = await enqueue(async () => {
    try {
      const ok = await updateScript(scriptId, {
        Game: { ClientPath: clientPath },
      })
      if (ok) {
        message.success(t(clientPath ? 'edit.clientPathSaved' : 'edit.clientPathReset'))
      } else {
        okwwConfig.Game.ClientPath = previousPath
      }
      return ok
    } catch (error) {
      okwwConfig.Game.ClientPath = previousPath
      throw error
    }
  })
  if (success && !clientPath && okwwConfig.Game.Type === 'Client') {
    // 清空手动指定后展示值重新来自解码，需要重新拉取，否则只剩占位符
    await refreshDerivedClientPath()
  }
  return success
}

const selectClientPath = async () => {
  if (!okwwConfig.Game.Enabled) return
  const paths = await window.electronAPI.selectFile([
    { name: '可执行文件', extensions: ['exe'] },
    { name: '所有文件', extensions: ['*'] },
  ])
  const picked = paths?.[0]
  if (!picked) return
  const normalized = picked.replace(/\\/g, '/')
  // 与后端 check() 同口径：按进程名精确匹配（大小写不同会被后端拒绝）
  const executable = normalized.split('/').pop()
  if (executable !== WUWA_CLIENT_EXECUTABLE) {
    showPathRejectModal(t('edit.invalidClientFileTitle'), t('edit.invalidClientFileContent'))
    return
  }
  await saveClientPath(normalized)
}

const resetClientPath = async () => {
  await saveClientPath('')
}

watch(
  () => okwwConfig.Game.Type,
  value => {
    // 初始化载入配置不保存；与最近一次发起/接受的目标值相同则无需重复提交。
    // 用「目标值」而非「已持久化值」：保存未返回期间切回原值也必须照常保存，
    // 否则后端的值与界面显示会分叉
    if (isInitializing.value || value === requestedLaunchType) return
    requestedLaunchType = value
    void handleLaunchTypeChange(value)
  }
)

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

.control-hint {
  display: block;
  margin-top: 4px;
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

.launch-type-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.derived-client-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
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
