<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link"> 脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="@/assets/hsr.png" alt="HSR" class="breadcrumb-logo" />
            编辑 HSR 脚本
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
    <a-card title="HSR 脚本配置" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="purple" class="type-tag"> HSR (三月七 / SRA) </a-tag>
      </template>

      <a-alert
        v-if="capabilitySnapshot?.unavailable_reason && !capabilitySnapshot?.warnings?.length"
        type="warning"
        show-icon
        :message="capabilitySnapshot.unavailable_reason"
        style="margin-bottom: 12px"
      />

      <a-alert
        v-for="warning in capabilitySnapshot?.warnings || []"
        :key="warning"
        type="warning"
        show-icon
        :message="warning"
        style="margin-bottom: 12px"
      />

      <a-form ref="formRef" :model="formData" layout="vertical" class="config-form">
        <!-- 脚本名称 -->
        <div class="form-section">
          <div class="section-header">
            <h3>基本信息</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="24">
              <a-form-item>
                <template #label>
                  <a-tooltip title="为 HSR 脚本设置一个易于识别的名称">
                    <span class="form-label">
                      脚本名称
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input
                  v-model:value="formData.infoName"
                  placeholder="请输入脚本名称"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('Info', 'Name', formData.infoName)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <a-alert
          type="info"
          show-icon
          class="user-control-notice"
          message="运行模式与任务配置已移至用户配置"
          description="请在用户页选择“MAS 管控”或“脚本直控”。两种模式都由 MAS 启动和关闭游戏；脚本页只维护安装路径与公共执行参数。"
        />

        <!-- M7A / SRA / 游戏路径 -->
        <div class="form-section">
          <div class="section-header">
            <h3>脚本与游戏配置</h3>
          </div>
          <div class="engine-path-hint">
            <a-typography-text type="secondary">
              填写对应脚本路径即启用该引擎；清空路径后，该引擎不再校验或参与调度。
            </a-typography-text>
          </div>
          <a-row :gutter="24">
            <a-col v-if="candidateEngines.has('M7A')" :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="March7th Assistant 安装目录（含 March7th Assistant.exe）">
                    <span class="form-label">
                      三月七路径
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="hsrConfig.M7A.Path"
                    placeholder="请选择三月七所在文件夹（含 March7th Assistant.exe）"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectPath('M7A.Path')">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择文件夹
                  </a-button>
                  <a-button
                    v-if="hsrConfig.M7A.Path"
                    title="清空三月七路径"
                    size="large"
                    class="path-clear-button"
                    @click="clearPath('M7A.Path')"
                  >
                    ×
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>

            <a-col v-if="candidateEngines.has('SRA')" :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="StarRailAssistant 安装目录（含 SRA-cli.exe）">
                    <span class="form-label">
                      SRA 路径
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="hsrConfig.SRA.Path"
                    placeholder="请选择 SRA 所在文件夹（含 SRA-cli.exe）"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectPath('SRA.Path')">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择文件夹
                  </a-button>
                  <a-button
                    v-if="hsrConfig.SRA.Path"
                    title="清空 SRA 路径"
                    size="large"
                    class="path-clear-button"
                    @click="clearPath('SRA.Path')"
                  >
                    ×
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24" style="margin-top: 16px">
            <a-col :xs="24" :lg="16">
              <a-form-item>
                <template #label>
                  <a-tooltip title="星穹铁道游戏根目录（含 StarRail.exe）">
                    <span class="form-label">
                      游戏路径
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="hsrConfig.Game.Path"
                    placeholder="请选择星穹铁道安装目录（含 StarRail.exe）"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectPath('Game.Path')">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择文件夹
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :xs="24" :lg="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="MAS 启动游戏后等待进入可操作状态的最长时间">
                    <span class="form-label">
                      游戏最大启动等待时间
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="hsrConfig.Game.WaitTime"
                  :min="0"
                  :max="9999"
                  addon-after="秒"
                  size="large"
                  style="width: 100%"
                  @change="handleGameConfigChange('WaitTime', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24" style="margin-top: 16px">
            <a-col :xs="24" :lg="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="启动星穹铁道时附加的命令行参数">
                    <span class="form-label">
                      游戏启动参数
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input
                  v-model:value="hsrConfig.Game.Arguments"
                  placeholder="请输入启动参数"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('Game', 'Arguments', hsrConfig.Game.Arguments)"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :lg="6">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="仅在 MAS 启动本地游戏前临时写入当前用户注册表并切为窗口模式；任务完成、失败或手动停止并关闭游戏后恢复原值"
                  >
                    <span class="form-label">
                      运行时设为 1920×1080 窗口模式
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <div class="game-toggle-option">
                  <a-switch
                    :checked="hsrConfig.Game.ForceResolution1920x1080"
                    @change="handleGameResolutionChange"
                  />
                  <a-typography-text type="secondary">结束后恢复原注册表值</a-typography-text>
                </div>
              </a-form-item>
            </a-col>
            <a-col :xs="24" :lg="6">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="每个用户在每个引擎上首次执行一次；以后仅当原生配置中的兑换码变化时再次兑换，其他奖励不受影响"
                  >
                    <span class="form-label">
                      兑换码仅在变化时执行
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <div class="game-toggle-option">
                  <a-switch
                    :checked="hsrConfig.Game.RedeemCodesOnlyWhenChanged"
                    @change="handleRedeemCodePolicyChange"
                  />
                  <a-typography-text type="secondary">新用户先执行一次</a-typography-text>
                </div>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 执行限制 -->
        <div class="form-section">
          <div class="section-header">
            <h3>执行限制</h3>
          </div>
          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item label="失败任务最大尝试次数">
                <a-input-number
                  v-model:value="hsrConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @change="handleRunConfigChange('RunTimesLimit', $event)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="日常任务超时限制（分钟）">
                <a-input-number
                  v-model:value="hsrConfig.Run.DailyTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @change="handleRunConfigChange('DailyTimeLimit', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="16">
            <a-col :span="24">
              <a-form-item label="周常任务超时限制（分钟）">
                <a-input-number
                  v-model:value="hsrConfig.Run.WeeklyTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @change="handleRunConfigChange('WeeklyTimeLimit', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { WS_ID_PLUGIN_SYSTEM, WS_PLUGIN_SNAPSHOT_UPDATED } from '@/services/websocket/types'
import {
  useHSRPluginApi,
  type HSREngine,
  type HSRCapabilitySnapshot,
} from '@/composables/useHSRPluginApi'
import { DEFAULT_HSR_TASK_MAPPING, type HSRManagedTaskConfig } from '@/types/script'

// HSR 内部非空 reactive 形态（OpenAPI 生成类型字段全部为 optional | null，
// 前端实际为非空；通过该形态消除 strict null 警告）。
type HSRConfigData = HSRManagedTaskConfig & {
  Info: { Name: string }
  Control: {
    Direct: boolean
    Engine: HSREngine
    TimeoutMinutes: number
  }
  SRA: { Path: string; Config: string }
  M7A: { Path: string; LowPerformanceMode: boolean }
  Game: {
    Backend: 'local' | 'mas_cloud' | 'native_owned'
    Path: string
    Arguments: string
    WaitTime: number
    ForceResolution1920x1080: boolean
    RedeemCodesOnlyWhenChanged: boolean
  }
  Run: {
    RunTimesLimit: number
    DailyTimeLimit: number
    WeeklyTimeLimit: number
  }
}

const logger = window.electronAPI.getLogger('HSR 脚本编辑')

const route = useRoute()
const router = useRouter()
const registryApi = useScriptRegistryApi()
const hsrPluginApi = useHSRPluginApi()
const { subscribe, unsubscribe } = useWebSocket()
const getScript = async (id: string) => (await registryApi.getScripts(id))[0] ?? null
const updateScript = async (id: string, config: Record<string, unknown>) => {
  await registryApi.updateScript(id, config)
  return true
}

const pageLoading = ref(false)
const scriptId = route.params.id as string
const isInitializing = ref(true)
const isSaving = ref(false)
const capabilitySnapshot = ref<HSRCapabilitySnapshot | null>(null)
let pluginSystemSubscriptionId: string | null = null

const formData = reactive({
  infoName: '',
})

const hsrConfig = reactive<HSRConfigData>({
  Info: { Name: '' },
  Control: { Direct: false, Engine: 'SRA', TimeoutMinutes: 120 },
  SRA: { Path: '', Config: '' },
  M7A: { Path: '', LowPerformanceMode: false },
  Game: {
    Backend: 'local',
    Path: '',
    Arguments: '',
    WaitTime: 60,
    ForceResolution1920x1080: false,
    RedeemCodesOnlyWhenChanged: true,
  },
  Run: {
    RunTimesLimit: 3,
    DailyTimeLimit: 20,
    WeeklyTimeLimit: 60,
  },
  TaskMapping: { ...DEFAULT_HSR_TASK_MAPPING },
  SRAReceiveRewards: {
    TrailblazerProfile: true,
    Assignments: true,
    Mail: true,
    DailyTraining: true,
    NamelessHonor: true,
    GiftOfOdyssey: true,
    RedeemCode: true,
  },
  SRADivergentUniverse: {
    RunTimes: 20,
    UseTechnique: false,
    PointRewards: true,
  },
  SRACurrencyWars: {
    Mode: 'normal',
    Difficulty: 'lowest',
    RunTimes: 1,
  },
  M7AReceiveRewards: {
    RunDailyTraining: true,
    UseSynthesis: true,
    UseHimekoTrial: false,
    UseMemoryOne: false,
    DailyCheckIn: true,
    Dispatch: true,
    Mail: true,
    Support: true,
    DailyTrainingReward: true,
    NamelessHonor: true,
    RedeemCode: true,
    Achievement: false,
    Messages: false,
  },
  M7ADivergentUniverse: {
    Mode: 'cycle',
    Level: 5,
    BonusEnabled: true,
  },
  M7ACurrencyWars: {
    Mode: 'normal',
    RankDifficulty: 'lowest',
    Strategy: 'aglaea',
    RestartOnSpecialTags: true,
    FastMode: false,
    BonusEnabled: true,
  },
  CultivationTarget: {
    Enabled: false,
    M7ARecognitionScheme: 'instance',
    M7AOrnamentWeeklyCount: 1,
    M7AUseUserStageWhenOnlyRelics: false,
  },
})

const candidateEngines = computed(
  () => new Set<HSREngine>(capabilitySnapshot.value?.candidate_engines || [])
)

// 需要后端语义化校正（DPAPI 加解密、路径规范化等）的字段保存后再 GET 拉回；
// 其余纯本地赋值字段不重复请求，避免覆盖用户刚改的值。
const FIELDS_REQUIRE_REFRESH_AFTER_SAVE = new Set<string>([
  'Info.Name',
  'M7A.Path',
  'SRA.Path',
  'Game.Path',
])

const handleChange = async (category: string, key: string, value: any) => {
  if (isInitializing.value || isSaving.value) return false
  isSaving.value = true
  try {
    const updateData: any = { [category]: { [key]: value } }
    const success = await updateScript(scriptId, updateData)
    if (!success) return false
    logger.info(`配置已保存: ${category}.${key}`)
    if (FIELDS_REQUIRE_REFRESH_AFTER_SAVE.has(`${category}.${key}`)) {
      await refreshScript()
    }
    return true
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
    message.error(`保存配置失败：${errorMsg}`)
    return false
  } finally {
    isSaving.value = false
  }
}

const refreshCapability = async () => {
  const snapshot = await hsrPluginApi.getCapabilities(scriptId)
  capabilitySnapshot.value = snapshot
  return snapshot
}

const handlePluginSystemMessage = () => {
  void refreshCapability().catch(error => logger.warn(`刷新 HSR 能力失败: ${String(error)}`))
}

const refreshScript = async () => {
  try {
    const scriptDetail = await getScript(scriptId)
    if (!scriptDetail) return
    formData.infoName = scriptDetail.name
    const cfg = scriptDetail.config as Partial<HSRConfigData>
    if (cfg.Info) Object.assign(hsrConfig.Info, cfg.Info)
    if (cfg.Control) Object.assign(hsrConfig.Control, cfg.Control)
    if (cfg.SRA) Object.assign(hsrConfig.SRA, cfg.SRA)
    if (cfg.M7A) Object.assign(hsrConfig.M7A, cfg.M7A)
    if (cfg.Game) {
      Object.assign(hsrConfig.Game, cfg.Game)
      if (!hsrConfig.Game.Backend) hsrConfig.Game.Backend = 'local'
      if (hsrConfig.Game.Arguments === undefined || hsrConfig.Game.Arguments === null) {
        hsrConfig.Game.Arguments = ''
      }
      if (hsrConfig.Game.WaitTime === undefined || hsrConfig.Game.WaitTime === null) {
        hsrConfig.Game.WaitTime = 60
      }
      if (
        hsrConfig.Game.ForceResolution1920x1080 === undefined ||
        hsrConfig.Game.ForceResolution1920x1080 === null
      ) {
        hsrConfig.Game.ForceResolution1920x1080 = false
      }
      if (
        hsrConfig.Game.RedeemCodesOnlyWhenChanged === undefined ||
        hsrConfig.Game.RedeemCodesOnlyWhenChanged === null
      ) {
        hsrConfig.Game.RedeemCodesOnlyWhenChanged = true
      }
    }
    if (!hsrConfig.Control.Engine) hsrConfig.Control.Engine = 'SRA'
    if (!hsrConfig.Control.TimeoutMinutes) hsrConfig.Control.TimeoutMinutes = 120
    if (hsrConfig.SRA.Config === undefined || hsrConfig.SRA.Config === null) {
      hsrConfig.SRA.Config = ''
    }
    if (cfg.Run) {
      Object.assign(hsrConfig.Run, cfg.Run)
      if (hsrConfig.Run.RunTimesLimit === undefined) hsrConfig.Run.RunTimesLimit = 3
      if (hsrConfig.Run.DailyTimeLimit === undefined) hsrConfig.Run.DailyTimeLimit = 20
      if (hsrConfig.Run.WeeklyTimeLimit === undefined) hsrConfig.Run.WeeklyTimeLimit = 60
    }
    if (cfg.TaskMapping) {
      hsrConfig.TaskMapping = { ...DEFAULT_HSR_TASK_MAPPING, ...cfg.TaskMapping }
    }
    if (cfg.SRAReceiveRewards) {
      Object.assign(hsrConfig.SRAReceiveRewards, cfg.SRAReceiveRewards)
    }
    if (cfg.SRADivergentUniverse) {
      Object.assign(hsrConfig.SRADivergentUniverse, cfg.SRADivergentUniverse)
    }
    if (cfg.SRACurrencyWars) {
      Object.assign(hsrConfig.SRACurrencyWars, cfg.SRACurrencyWars)
    }
    if (cfg.M7AReceiveRewards) {
      Object.assign(hsrConfig.M7AReceiveRewards, cfg.M7AReceiveRewards)
    }
    if (cfg.M7ADivergentUniverse) {
      Object.assign(hsrConfig.M7ADivergentUniverse, cfg.M7ADivergentUniverse)
    }
    if (cfg.M7ACurrencyWars) {
      Object.assign(hsrConfig.M7ACurrencyWars, cfg.M7ACurrencyWars)
    }
    if (cfg.CultivationTarget) {
      Object.assign(hsrConfig.CultivationTarget, cfg.CultivationTarget)
    }
    await refreshCapability()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`刷新配置失败: ${errorMsg}`)
  }
}

const handleRunConfigChange = async (key: string, value: any) => {
  if (isInitializing.value || isSaving.value) return
  isSaving.value = true
  try {
    const updateData: any = { Run: { [key]: value } }
    const success = await updateScript(scriptId, updateData)
    if (!success) return
    logger.info(`配置已保存: Run.${key}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const handleGameConfigChange = async (key: 'WaitTime', value: number | null) => {
  if (isInitializing.value || isSaving.value) return
  const normalizedValue = value ?? 60
  hsrConfig.Game[key] = normalizedValue
  const saved = await handleChange('Game', key, normalizedValue)
  if (!saved) await refreshScript()
}

const handleGameResolutionChange = async (value: boolean | string | number) => {
  if (isInitializing.value || isSaving.value) return
  const enabled = Boolean(value)
  hsrConfig.Game.ForceResolution1920x1080 = enabled
  const saved = await handleChange('Game', 'ForceResolution1920x1080', enabled)
  if (!saved) await refreshScript()
}

const handleRedeemCodePolicyChange = async (value: boolean | string | number) => {
  if (isInitializing.value || isSaving.value) return
  const enabled = Boolean(value)
  hsrConfig.Game.RedeemCodesOnlyWhenChanged = enabled
  const saved = await handleChange('Game', 'RedeemCodesOnlyWhenChanged', enabled)
  if (!saved) await refreshScript()
}

// 路径选择时需校验的 exe 名（key -> exe 文件名）
const PATH_VALIDATION: Record<string, string> = {
  'M7A.Path': 'March7th Assistant.exe',
  'SRA.Path': 'SRA-cli.exe',
  'Game.Path': 'StarRail.exe',
}

const joinPath = (folder: string, fileName: string) =>
  `${folder.replace(/[\\/]+$/g, '')}/${fileName}`

const selectPath = async (key: string) => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }
    const path = await window.electronAPI.selectFolder()
    if (!path) return

    // 校验目录下是否存在期望的 exe；校验失败弹 Modal.warning 且不保存
    const expectedExe = PATH_VALIDATION[key]
    if (expectedExe) {
      const exePath = joinPath(path, expectedExe)
      const exists = await window.electronAPI.fileExists(exePath)
      if (!exists) {
        Modal.warning({
          title: '路径无效',
          content: `所选目录下未找到 ${expectedExe}，请重新选择正确的安装目录。`,
        })
        return
      }
    }

    let saved = false
    if (key === 'M7A.Path') {
      saved = await handleChange('M7A', 'Path', path)
    } else if (key === 'SRA.Path') {
      saved = await handleChange('SRA', 'Path', path)
    } else if (key === 'Game.Path') {
      saved = await handleChange('Game', 'Path', path)
    } else {
      logger.warn(`未知的路径 key: ${key}`)
      return
    }
    if (!saved) return
    message.success('路径已选择')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择路径失败: ${errorMsg}`)
    message.error('选择文件夹失败')
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

// 清空路径：保存空字符串到后端，然后级联重排 TaskMapping。
const clearPath = async (key: string) => {
  if (key === 'M7A.Path') {
    const saved = await handleChange('M7A', 'Path', '')
    if (saved) hsrConfig.M7A.Path = ''
  } else if (key === 'SRA.Path') {
    const saved = await handleChange('SRA', 'Path', '')
    if (saved) hsrConfig.SRA.Path = ''
  }
}

onMounted(async () => {
  pluginSystemSubscriptionId = subscribe(
    { id: WS_ID_PLUGIN_SYSTEM, type: WS_PLUGIN_SNAPSHOT_UPDATED },
    handlePluginSystemMessage
  )
  pageLoading.value = true
  try {
    const scriptDetail = await getScript(scriptId)
    if (!scriptDetail) {
      message.error('脚本不存在或加载失败')
      router.push('/scripts')
      return
    }
    if (scriptDetail.type !== 'HSR' || scriptDetail.editor_kind !== 'plugin:automas_script_hsr') {
      message.error('当前脚本未启用 HSR 插件编辑器')
      router.push('/scripts')
      return
    }
    await refreshScript()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    message.error('加载脚本失败')
    router.push('/scripts')
  } finally {
    pageLoading.value = false
    isInitializing.value = false
  }
})

onUnmounted(() => {
  if (pluginSystemSubscriptionId) unsubscribe(pluginSystemSubscriptionId)
})
</script>

<style scoped>
.engine-path-hint {
  margin-bottom: 16px;
}

.user-control-notice {
  margin-bottom: 20px;
}

.game-toggle-option {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 40px;
}

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
  transition: color 0.3s ease;
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
  border-radius: 16px;
  box-shadow: none;
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
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
  background: var(--ant-color-primary);
  border-radius: 2px;
}

.section-hint {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  margin: 4px 0 12px 0;
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
  box-shadow: 0 0 0 4px var(--ant-color-primary-bg);
}

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid var(--ant-color-border);
  transition: all 0.3s ease;
}

.path-input-group:hover {
  border-color: var(--ant-color-primary-hover);
}

.path-input-group:focus-within {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px var(--ant-color-primary-bg);
}

.path-input-group :deep(.path-input.ant-input) {
  flex: 1;
  border: none;
  border-radius: 0;
  background: var(--ant-color-bg-container);
}

.path-input-group :deep(.path-input.ant-input:focus) {
  box-shadow: none;
}

.path-button {
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  transition: all 0.3s ease;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.path-button:hover {
  background: var(--ant-color-primary);
  color: white;
  transform: none;
}

.path-clear-button {
  border: none;
  border-radius: 0;
  background: var(--ant-color-error-bg);
  color: var(--ant-color-error);
  font-weight: 700;
  font-size: 18px;
  padding: 0 16px;
  transition: all 0.3s ease;
  border-left: 1px solid var(--ant-color-border-secondary);
  min-width: 48px;
}

.path-clear-button:hover {
  background: var(--ant-color-error);
  color: white;
}

.cancel-button {
  height: 40px;
}
</style>
