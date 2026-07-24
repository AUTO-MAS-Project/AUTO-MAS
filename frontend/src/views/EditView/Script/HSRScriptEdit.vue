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
            <a-col :span="24">
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
          <a-row :gutter="16">
            <a-col v-if="effectiveEngines.has('M7A')" :span="12">
              <a-form-item label="启用低性能兼容模式">
                <a-switch
                  v-model:checked="hsrConfig.M7A.LowPerformanceMode"
                  :disabled="!hsrConfig.M7A.Path"
                  @change="handleM7AConfigChange('LowPerformanceMode', $event)"
                />
                <div class="form-item-hint">
                  仅对三月七差分宇宙生效，映射到 weekly_divergent_stable_mode
                </div>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 模块脚本分配 -->
        <div v-if="effectiveEngines.size > 1" class="form-section">
          <div class="section-header">
            <h3>模块脚本分配</h3>
          </div>
          <p class="section-hint">
            指定每个模块由三月七还是 SRA 执行。Auto-MAS 会按此映射构造 SRA / 三月七执行计划。
          </p>
          <a-row :gutter="24">
            <a-col v-for="m in moduleList" :key="m.key" :span="12" style="margin-top: 12px">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ m.label }}
                    <a-tooltip :title="getModuleHint(m.key)">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  :value="getTaskMapping(m.key)"
                  size="large"
                  :disabled="!isModuleSelectable()"
                  :placeholder="getModulePlaceholder()"
                  :options="getModuleOptions()"
                  @change="handleTaskMappingChange(m.key, $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 培养目标 -->
        <div class="form-section">
          <div class="section-header">
            <h3>培养目标</h3>
          </div>
          <p class="section-hint">
            由当前 TaskMapping.Daily 选中的引擎使用其原生培养目标能力。 SRA 模式下历战余响也由 SRA
            培养目标决定，MAS 仅按实际日志回写完成状态。
          </p>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="启用后，由 TaskMapping.Daily 选中的引擎使用其原生培养目标能力">
                    <span class="form-label">
                      启用培养目标
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-switch
                  v-model:checked="hsrConfig.CultivationTarget.Enabled"
                  @change="handleCultivationTargetChange('Enabled', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24" style="margin-top: 16px">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="instance=按副本名称识别，drop=按副本素材识别">
                    <span class="form-label">
                      M7A 识别方案
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="hsrConfig.CultivationTarget.M7ARecognitionScheme"
                  :disabled="!hsrConfig.CultivationTarget.Enabled"
                  size="large"
                  style="width: 100%"
                  :options="[
                    { value: 'instance', label: '按副本名称识别' },
                    { value: 'drop', label: '按副本素材识别' },
                  ]"
                  @change="handleCultivationTargetChange('M7ARecognitionScheme', $event)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="M7A 饰品提取每周执行次数（0-7）">
                    <span class="form-label">
                      M7A 饰品提取周次数
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="hsrConfig.CultivationTarget.M7AOrnamentWeeklyCount"
                  :min="0"
                  :max="7"
                  :disabled="!hsrConfig.CultivationTarget.Enabled"
                  size="large"
                  style="width: 100%"
                  @change="handleCultivationTargetChange('M7AOrnamentWeeklyCount', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24" style="margin-top: 16px">
            <a-col :span="24">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="当培养目标只识别到侵蚀隧洞和饰品提取时，是否改用用户手动配置的副本"
                  >
                    <span class="form-label">
                      M7A 仅遗器时使用手动副本
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-switch
                  v-model:checked="hsrConfig.CultivationTarget.M7AUseUserStageWhenOnlyRelics"
                  :disabled="!hsrConfig.CultivationTarget.Enabled"
                  @change="handleCultivationTargetChange('M7AUseUserStageWhenOnlyRelics', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 周常任务执行策略 -->
        <div class="form-section">
          <div class="section-header">
            <h3>周常任务执行策略</h3>
          </div>
          <p class="section-hint">
            根据上方模块脚本分配的选择，差分宇宙 / 货币战争会按下表策略执行。
            用户页不再需要配置这些参数；只有货币战争的"开拓者名称"在用户页填写。
          </p>

          <!-- 差分宇宙模板 -->
          <a-row :gutter="24" style="margin-top: 12px">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">差分宇宙</span>
                </template>
                <a-alert v-if="getTaskMapping('DivergentUniverse') === 'SRA'" type="info" show-icon>
                  <template #message>
                    <div>SRA 执行策略：</div>
                    <div>- 差分宇宙乐园漫记</div>
                    <div>- 模式刷第一关</div>
                    <div>- 次数 20</div>
                    <div>- 启用积分奖励</div>
                  </template>
                </a-alert>
                <a-alert
                  v-else-if="getTaskMapping('DivergentUniverse') === 'M7A'"
                  type="info"
                  show-icon
                >
                  <template #message>
                    <div>三月七执行策略：</div>
                    <div>- 启用积分奖励</div>
                    <div>- 周期演算</div>
                    <div>
                      - 低性能兼容模式：{{ hsrConfig.M7A.LowPerformanceMode ? '启用' : '关闭' }}
                    </div>
                    <div style="margin-top: 4px; color: var(--ant-color-text-tertiary)">
                      其它 DU 字段（球队 / 赐福 / 演算策略）由三月七客户端自行决定
                    </div>
                  </template>
                </a-alert>
                <a-alert
                  v-else
                  type="warning"
                  show-icon
                  message="请先配置至少一个已加载 HSR 引擎的路径"
                />
              </a-form-item>
            </a-col>

            <!-- 货币战争执行策略 -->
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">货币战争</span>
                </template>
                <a-alert v-if="getTaskMapping('CurrencyWars') === 'SRA'" type="info" show-icon>
                  <template #message>
                    <div>SRA 执行策略：</div>
                    <div>- 标准博弈</div>
                    <div>- 最低难度</div>
                    <div>- SRA 保存的第一套攻略</div>
                    <div>- 运行次数 1</div>
                    <div>- 开拓者名称：从用户页读取</div>
                    <div class="strategy-warning">
                      - 重点提示：SRA 货币战争不会自动领取积分奖励，请在游戏内手动领取。
                    </div>
                  </template>
                </a-alert>
                <a-alert v-else-if="getTaskMapping('CurrencyWars') === 'M7A'" type="info" show-icon>
                  <template #message>
                    <div>三月七执行策略：</div>
                    <div>- 启用积分奖励</div>
                    <div>- 标准博弈</div>
                    <div>- 最低职级</div>
                    <div>- 阿格莱雅策略</div>
                    <div>- 特定词条接受重开</div>
                    <div>- 开拓者名称：从用户页读取</div>
                  </template>
                </a-alert>
                <a-alert
                  v-else
                  type="warning"
                  show-icon
                  message="请先配置至少一个已加载 HSR 引擎的路径"
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
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'
import {
  useHSRPluginApi,
  type HSREngine,
  type HSRCapabilitySnapshot,
} from '@/composables/useHSRPluginApi'
import { DEFAULT_HSR_TASK_MAPPING, resolveTaskMappingValue } from '@/types/script'
import { buildHSRCapabilityView } from '@/views/HSRUserEdit/capabilityView'

type HSRTaskMapping = Partial<
  Record<'Daily' | 'ReceiveRewards' | 'DivergentUniverse' | 'CurrencyWars', HSREngine>
>

// HSR 内部非空 reactive 形态（OpenAPI 生成类型字段全部为 optional | null，
// 前端实际为非空；通过该形态消除 strict null 警告）。
type HSRConfigData = {
  Info: { Name: string }
  SRA: { Path: string }
  M7A: { Path: string; LowPerformanceMode: boolean }
  Game: { Path: string; Arguments: string; WaitTime: number }
  Run: {
    RunTimesLimit: number
    DailyTimeLimit: number
    WeeklyTimeLimit: number
  }
  TaskMapping: HSRTaskMapping
  CultivationTarget: {
    Enabled: boolean
    M7ARecognitionScheme: 'instance' | 'drop'
    M7AOrnamentWeeklyCount: number
    M7AUseUserStageWhenOnlyRelics: boolean
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

const handlePluginSystemMessage = (message: WebSocketBaseMessage) => {
  const payload = message.data as { kind?: string } | undefined
  if (payload?.kind !== 'snapshot') return
  void hsrPluginApi
    .getCapabilities(scriptId)
    .then(snapshot => (capabilitySnapshot.value = snapshot))
    .catch(error => logger.warn(`刷新 HSR 能力失败: ${String(error)}`))
}

const formData = reactive({
  infoName: '',
})

const hsrConfig = reactive<HSRConfigData>({
  Info: { Name: '' },
  SRA: { Path: '' },
  M7A: { Path: '', LowPerformanceMode: false },
  Game: { Path: '', Arguments: '', WaitTime: 60 },
  Run: {
    RunTimesLimit: 3,
    DailyTimeLimit: 20,
    WeeklyTimeLimit: 60,
  },
  TaskMapping: { ...DEFAULT_HSR_TASK_MAPPING },
  CultivationTarget: {
    Enabled: false,
    M7ARecognitionScheme: 'instance',
    M7AOrnamentWeeklyCount: 1,
    M7AUseUserStageWhenOnlyRelics: false,
  },
})

const moduleList = [
  { key: 'Daily', label: '体力', tooltip: '开拓力 / 遗器 / 历战余响' },
  { key: 'ReceiveRewards', label: '日常与奖励', tooltip: '兑换码 / 邮件 / 委托 / 勋礼 / 每日实训' },
  { key: 'DivergentUniverse', label: '差分宇宙', tooltip: '差分宇宙刷取' },
  { key: 'CurrencyWars', label: '货币战争', tooltip: 'PVP 货币战争' },
] as const

const capabilityView = computed(() => buildHSRCapabilityView(capabilitySnapshot.value))
const effectiveEngines = computed(() => capabilityView.value.effectiveEngines)
const candidateEngines = computed(
  () => new Set<HSREngine>(capabilitySnapshot.value?.candidate_engines || [])
)

// 路径变更后重排 TaskMapping 的判断已统一到 getModuleOptions / reconcileTaskMapping。
// 不再保留静态 engineOptions。

// 需要后端语义化校正（DPAPI 加解密、路径规范化等）的字段保存后再 GET 拉回；
// 其余纯本地赋值字段不重复请求，避免覆盖用户刚改的值。
const FIELDS_REQUIRE_REFRESH_AFTER_SAVE = new Set<string>([
  'Info.Name',
  'M7A.Path',
  'SRA.Path',
  'Game.Path',
])

const handleChange = async (category: string, key: string, value: any) => {
  if (isInitializing.value || isSaving.value) return
  isSaving.value = true
  try {
    const updateData: any = { [category]: { [key]: value } }
    const success = await updateScript(scriptId, updateData)
    if (!success) return
    logger.info(`配置已保存: ${category}.${key}`)
    if (FIELDS_REQUIRE_REFRESH_AFTER_SAVE.has(`${category}.${key}`)) {
      await refreshScript()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

// 当前可用脚本集合由插件注册表与脚本选择求交得到。
const availableScripts = computed<Set<'M7A' | 'SRA'>>(() => {
  return new Set(effectiveEngines.value)
})

// 任意可用路径都未配置
const noPathConfigured = computed(() => availableScripts.value.size === 0)

// 单个模块在当前路径下的可选项。
const getModuleOptions = (): Array<{ value: 'M7A' | 'SRA'; label: string }> => {
  const out: Array<{ value: 'M7A' | 'SRA'; label: string }> = []
  if (availableScripts.value.has('M7A')) out.push({ value: 'M7A', label: '三月七' })
  if (availableScripts.value.has('SRA')) out.push({ value: 'SRA', label: 'SRA' })
  return out
}

// 该模块当前是否可选择
const isModuleSelectable = () => getModuleOptions().length > 0

// select 当前显示值；无可用路径时返回 undefined，避免显示默认值误导
const getTaskMapping = (k: keyof HSRTaskMapping): 'M7A' | 'SRA' | undefined => {
  if (noPathConfigured.value) return undefined
  return resolveTaskMappingValue(hsrConfig.TaskMapping?.[k], availableScripts.value)
}

const getModulePlaceholder = () => {
  if (noPathConfigured.value) return '请先配置脚本路径'
  return undefined
}

const getModuleHint = (moduleKey: string) => {
  const baseTooltip = moduleList.find(m => m.key === moduleKey)?.tooltip ?? ''
  if (noPathConfigured.value) {
    return `${baseTooltip}\n请先配置三月七或 SRA 脚本路径`
  }
  return baseTooltip
}

const refreshScript = async () => {
  try {
    const scriptDetail = await getScript(scriptId)
    if (!scriptDetail) return
    formData.infoName = scriptDetail.name
    const cfg = scriptDetail.config as Partial<HSRConfigData>
    if (cfg.Info) Object.assign(hsrConfig.Info, cfg.Info)
    if (cfg.SRA) Object.assign(hsrConfig.SRA, cfg.SRA)
    if (cfg.M7A) Object.assign(hsrConfig.M7A, cfg.M7A)
    if (cfg.Game) {
      Object.assign(hsrConfig.Game, cfg.Game)
      if (hsrConfig.Game.Arguments === undefined || hsrConfig.Game.Arguments === null) {
        hsrConfig.Game.Arguments = ''
      }
      if (hsrConfig.Game.WaitTime === undefined || hsrConfig.Game.WaitTime === null) {
        hsrConfig.Game.WaitTime = 60
      }
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
    if (cfg.CultivationTarget) {
      Object.assign(hsrConfig.CultivationTarget, cfg.CultivationTarget)
      if (
        hsrConfig.CultivationTarget.M7ARecognitionScheme !== 'instance' &&
        hsrConfig.CultivationTarget.M7ARecognitionScheme !== 'drop'
      ) {
        hsrConfig.CultivationTarget.M7ARecognitionScheme = 'instance'
      }
      if (typeof hsrConfig.CultivationTarget.M7AOrnamentWeeklyCount !== 'number') {
        hsrConfig.CultivationTarget.M7AOrnamentWeeklyCount = 1
      }
    }
    capabilitySnapshot.value = await hsrPluginApi.getCapabilities(scriptId)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`刷新配置失败: ${errorMsg}`)
  }
}

const handleTaskMappingChange = (module: string, value: 'M7A' | 'SRA') => {
  // 检查当前值是否与要保存的值一致，避免无意义保存
  const current = hsrConfig.TaskMapping?.[module as keyof HSRTaskMapping]
  if (current === value) return
  if (!hsrConfig.TaskMapping) hsrConfig.TaskMapping = {}
  hsrConfig.TaskMapping[module as keyof HSRTaskMapping] = value
  handleChange('TaskMapping', module, value)
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

const handleM7AConfigChange = async (key: string, value: unknown) => {
  await handleChange('M7A', key, value)
}

const handleCultivationTargetChange = async (key: string, value: unknown) => {
  await handleChange('CultivationTarget', key, value)
}

const handleGameConfigChange = async (key: 'WaitTime', value: number | null) => {
  if (isInitializing.value || isSaving.value) return
  const normalizedValue = value ?? 60
  hsrConfig.Game[key] = normalizedValue
  await handleChange('Game', key, normalizedValue)
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

    if (key === 'M7A.Path') {
      await handleChange('M7A', 'Path', path)
    } else if (key === 'SRA.Path') {
      await handleChange('SRA', 'Path', path)
    } else if (key === 'Game.Path') {
      await handleChange('Game', 'Path', path)
    } else {
      logger.warn(`未知的路径 key: ${key}`)
      return
    }
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
    await handleChange('M7A', 'Path', '')
    hsrConfig.M7A.Path = ''
  } else if (key === 'SRA.Path') {
    await handleChange('SRA', 'Path', '')
    hsrConfig.SRA.Path = ''
  }
}

onMounted(async () => {
  pluginSystemSubscriptionId = subscribe({ id: 'PluginSystem' }, handlePluginSystemMessage)
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

.strategy-warning {
  margin-top: 8px;
  color: var(--ant-color-warning);
  font-weight: 600;
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
