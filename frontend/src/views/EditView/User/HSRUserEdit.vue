<template>
  <div class="user-edit-container">
    <div class="user-edit-header">
      <div class="header-nav">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts" class="breadcrumb-link"> 脚本管理</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>{{ scriptName || 'HSR' }}</a-breadcrumb-item>
        </a-breadcrumb>
        <h1>
          <img src="@/assets/hsr.png" alt="" class="page-logo" />
          {{ isEdit ? '编辑 HSR 用户' : '添加 HSR 用户' }}
        </h1>
        <p>SRA / 三月七任务、培养目标、体力关卡和执行进度会在操作后即时保存</p>
      </div>
      <a-button class="cancel-button" @click="handleCancel">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
    </div>

    <div class="user-edit-content">
      <a-alert
        v-if="saveError"
        type="error"
        show-icon
        closable
        class="save-error"
        :message="saveError"
        @close="saveError = ''"
      />
      <a-spin :spinning="isSaving" class="config-shell">
        <a-alert
          v-for="warning in capabilitySnapshot?.warnings || []"
          :key="warning"
          type="warning"
          show-icon
          :message="warning"
          style="margin-bottom: 12px"
        />
        <a-form ref="formRef" :model="formData" layout="vertical" class="config-form">
          <!-- 基本信息 -->
          <div class="form-section">
            <div class="section-header"><h3>基本信息</h3></div>
            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="该名称也会作为货币战争的开拓者名称写入 M7A/SRA">
                      <span class="form-label"
                        >用户名 <QuestionCircleOutlined class="help-icon"
                      /></span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Name"
                    size="large"
                    class="modern-input"
                    @blur="handleFieldSave('Info.Name', formData.Info.Name)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="4">
                <a-form-item>
                  <template #label>
                    <span class="form-label">启用</span>
                  </template>
                  <a-select
                    v-model:value="formData.Info.Status"
                    size="large"
                    @change="handleFieldSave('Info.Status', formData.Info.Status)"
                  >
                    <a-select-option :value="true">是</a-select-option>
                    <a-select-option :value="false">否</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col v-if="effectiveEngines.has('SRA')" :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">账号</span>
                  </template>
                  <div class="sensitive-field">
                    <a-input
                      :value="sraIdDraft"
                      :placeholder="sraIdPlaceholder"
                      autocomplete="off"
                      size="large"
                      class="modern-input"
                      @update:value="sraIdDraft = $event"
                    />
                    <div class="sensitive-actions">
                      <span class="sensitive-hint">原值不会回显；留空保持原值</span>
                      <a-space size="small">
                        <a-button
                          v-if="hasStoredSraId"
                          danger
                          size="small"
                          @click="clearSraCredential('SRA.Id')"
                        >
                          清空
                        </a-button>
                        <a-button
                          type="primary"
                          size="small"
                          :disabled="!sraIdDraft"
                          @click="saveSraCredential('SRA.Id', sraIdDraft)"
                        >
                          保存
                        </a-button>
                      </a-space>
                    </div>
                  </div>
                </a-form-item>
              </a-col>
              <a-col v-if="effectiveEngines.has('SRA')" :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">密码</span>
                  </template>
                  <div class="sensitive-field">
                    <a-input-password
                      :value="sraPasswordDraft"
                      :placeholder="sraPasswordPlaceholder"
                      autocomplete="new-password"
                      size="large"
                      :input-class="'modern-input'"
                      @update:value="sraPasswordDraft = $event"
                    />
                    <div class="sensitive-actions">
                      <span class="sensitive-hint">原值不会回显；留空保持原值</span>
                      <a-space size="small">
                        <a-button
                          v-if="hasStoredSraPassword"
                          danger
                          size="small"
                          @click="clearSraCredential('SRA.Password')"
                        >
                          清空
                        </a-button>
                        <a-button
                          type="primary"
                          size="small"
                          :disabled="!sraPasswordDraft"
                          @click="saveSraCredential('SRA.Password', sraPasswordDraft)"
                        >
                          保存
                        </a-button>
                      </a-space>
                    </div>
                  </div>
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="24" style="margin-top: 8px">
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">服务器</span>
                  </template>
                  <a-select
                    v-model:value="formData.Info.Server"
                    size="large"
                    :options="serverOptions"
                    @change="handleFieldSave('Info.Server', formData.Info.Server)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <a-tooltip
                      title="剩余天数，-1 表示不限制；0 表示今日到期；正数表示距到期还剩 N 天"
                    >
                      <span class="form-label"
                        >剩余天数 <QuestionCircleOutlined class="help-icon"
                      /></span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="formData.Info.RemainedDay"
                    :min="-1"
                    :max="9999"
                    size="large"
                    style="width: 100%"
                    @blur="handleFieldSave('Info.RemainedDay', formData.Info.RemainedDay)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">备注</span>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Notes"
                    size="large"
                    class="modern-input"
                    @blur="handleFieldSave('Info.Notes', formData.Info.Notes)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-alert
              v-if="effectiveEngines.has('SRA')"
              type="info"
              show-icon
              style="margin-top: 8px"
              message="保存时 MAS 会自动加密账号密码。未配置 SRA 或未使用 SRA 模块时，账号密码不会用于切号。"
            />
          </div>

          <!-- 每日任务 -->
          <div class="form-section">
            <div class="section-header"><h3>每日任务</h3></div>
            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item label="体力">
                  <a-switch
                    v-model:checked="formData.TaskSwitch.Daily"
                    checked-children="开启"
                    un-checked-children="关闭"
                    :loading="isSaving"
                    @change="(checked: boolean) => handleTaskSwitchToggle('Daily', checked)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="日常与奖励">
                  <a-switch
                    v-model:checked="formData.TaskSwitch.ReceiveRewards"
                    checked-children="开启"
                    un-checked-children="关闭"
                    :loading="isSaving"
                    @change="
                      (checked: boolean) => handleTaskSwitchToggle('ReceiveRewards', checked)
                    "
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <!-- 日常与奖励执行策略（按 TaskMapping.ReceiveRewards 动态展示） -->
            <a-alert
              v-if="
                formData.TaskSwitch.ReceiveRewards && getTaskMapping('ReceiveRewards') === 'M7A'
              "
              type="info"
              show-icon
              style="margin-top: 12px"
            >
              <template #message>
                <div>三月七「日常与奖励」执行策略：</div>
                <div>- 每日实训：开启</div>
                <div>- 每日实训的合成材料：开启</div>
                <div>- 活动检测：开启</div>
                <div>- 活动检测的每日签到：开启</div>
                <div>
                  - 奖励领取：开启，领取 委托奖励 / 邮件奖励 / 每日实训奖励 / 无名勋礼奖励 / 兑换码
                </div>
                <div>- 不领取：成就奖励、短信奖励</div>
              </template>
            </a-alert>
            <a-alert
              v-else-if="
                formData.TaskSwitch.ReceiveRewards && getTaskMapping('ReceiveRewards') === 'SRA'
              "
              type="info"
              show-icon
              style="margin-top: 12px"
            >
              <template #message>
                <div>SRA「日常与奖励」执行策略：</div>
                <div>
                  - 当前维护的奖励项全部领取：委托奖励 / 邮件奖励 / 每日实训奖励 / 无名勋礼奖励 /
                  兑换码
                </div>
                <div>- 新增奖励不会自动领取，需更新适配后才会领取</div>
              </template>
            </a-alert>
          </div>

          <!-- 周常：差分宇宙/货币战争 -->
          <div class="form-section">
            <div class="section-header"><h3>周常</h3></div>
            <a-form-item label="差分/货币">
              <a-select
                :value="weeklyTaskMode"
                size="large"
                :loading="isSaving"
                :disabled="isSaving"
                @change="handleWeeklyTaskModeChange"
              >
                <a-select-option value="off">关闭</a-select-option>
                <a-select-option value="DivergentUniverse">差分宇宙</a-select-option>
                <a-select-option value="CurrencyWars">货币战争</a-select-option>
              </a-select>
            </a-form-item>

            <!-- 差分宇宙执行策略：按 TaskMapping 动态显示 M7A/SRA -->
            <div v-if="weeklyTaskMode === 'DivergentUniverse'" class="weekly-subblock">
              <a-alert v-if="getTaskMapping('DivergentUniverse') === 'M7A'" type="info" show-icon>
                <template #message>
                  <div>三月七差分宇宙执行策略：</div>
                  <div>- 启用积分奖励</div>
                  <div>- 周期演算</div>
                  <div>- 低性能兼容模式：跟随脚本页「启用低性能兼容模式」开关</div>
                  <div style="margin-top: 8px; color: var(--ant-color-text-tertiary)">
                    请提前在 HSR 内配好差分宇宙队伍（球队 / 赐福 /
                    演算策略由三月七客户端自行决定）。
                  </div>
                </template>
              </a-alert>
              <a-alert
                v-else-if="getTaskMapping('DivergentUniverse') === 'SRA'"
                type="info"
                show-icon
              >
                <template #message>
                  <div>SRA 差分宇宙执行策略：</div>
                  <div>- 差分宇宙乐园漫记</div>
                  <div>- 模式刷第一关</div>
                  <div>- 次数 20</div>
                  <div>- 启用积分奖励</div>
                  <div style="margin-top: 8px; color: var(--ant-color-text-tertiary)">
                    请提前在 HSR 内配好差分宇宙队伍。
                  </div>
                </template>
              </a-alert>
              <a-alert
                v-else
                type="warning"
                show-icon
                message="请先在脚本页配置至少一个已加载 HSR 引擎的路径"
              />
            </div>

            <!-- 货币战争执行策略：开拓者名称跟随用户名 + 按 TaskMapping 动态显示 -->
            <div v-if="weeklyTaskMode === 'CurrencyWars'" class="weekly-subblock">
              <a-row :gutter="24" style="margin-bottom: 12px">
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">开拓者名称</span>
                    </template>
                    <a-input
                      :value="currencyWarsTrailblazerName"
                      size="large"
                      class="modern-input readonly-display"
                      readonly
                    />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-alert v-if="getTaskMapping('CurrencyWars') === 'M7A'" type="info" show-icon>
                <template #message>
                  <div>三月七货币战争执行策略：</div>
                  <div>- 启用积分奖励</div>
                  <div>- 标准博弈</div>
                  <div>- 最低职级</div>
                  <div>- 阿格莱雅策略</div>
                  <div>- 特定词条接受重开</div>
                  <div>- 开拓者名称：使用上方「用户名」</div>
                </template>
              </a-alert>
              <a-alert v-else-if="getTaskMapping('CurrencyWars') === 'SRA'" type="info" show-icon>
                <template #message>
                  <div>SRA 货币战争执行策略：</div>
                  <div>- 标准博弈</div>
                  <div>- 最低难度</div>
                  <div>- SRA 保存的第一套模板</div>
                  <div>- 运行次数 1</div>
                  <div>- 开拓者名称：使用上方「用户名」</div>
                  <div class="strategy-warning">
                    - 重点提示：SRA 货币战争不会自动领取积分奖励，请在游戏内手动领取。
                  </div>
                </template>
              </a-alert>
              <a-alert
                v-else
                type="warning"
                show-icon
                message="请先在脚本页配置至少一个已加载 HSR 引擎的路径"
              />
            </div>
          </div>

          <!-- 关卡配置 -->
          <StageConfigSection
            v-if="dailyTaskEngine"
            :form-data="formData"
            :loading="isSaving"
            :daily-engine="dailyTaskEngine"
            :stage-options="hsrStageOptions"
            :stage-options-loading="hsrStageOptionsLoading"
            :stage-options-error="hsrStageOptionsError"
            @save="handleFieldSave"
          />
          <div v-else class="form-section">
            <div class="section-header"><h3>体力配置</h3></div>
            <a-alert
              type="warning"
              show-icon
              message="请先在脚本页配置至少一个已加载 HSR 引擎的路径后，再配置体力关卡。"
            />
          </div>

          <!-- 进度与重置 (历战余响开始日 已下沉到 体力配置 区) -->
          <div class="form-section">
            <div class="section-header"><h3>进度与重置</h3></div>

            <!-- 历战余响进度 -->
            <a-row :gutter="24" align="middle">
              <a-col :span="10">
                <div class="progress-group">
                  <span class="progress-label">历战余响</span>
                  <a-tag :color="eowCompletedThisWeek ? 'green' : 'orange'">
                    本周 {{ eowCompletedThisWeek ? '已完成' : '未完成' }}
                  </a-tag>
                  <span
                    v-if="hasValidCompletionDate(formData.Data.EchoOfWarLastCompletionDate)"
                    class="date-hint"
                  >
                    最近完成：{{ formData.Data.EchoOfWarLastCompletionDate }}
                  </span>
                </div>
              </a-col>
              <a-col :span="14">
                <a-space>
                  <a-button size="small" :disabled="eowCompletedThisWeek" @click="markEowCompleted">
                    标记完成
                  </a-button>
                  <a-button size="small" danger @click="resetEowProgress"> 重置 </a-button>
                </a-space>
              </a-col>
            </a-row>

            <!-- 周常进度 -->
            <a-row :gutter="24" align="middle" style="margin-top: 16px">
              <a-col :span="10">
                <div class="progress-group">
                  <span class="progress-label">周常</span>
                  <a-tag :color="formData.Data.WeeklyCompletedThisWeek ? 'green' : 'orange'">
                    本周 {{ formData.Data.WeeklyCompletedThisWeek ? '已完成' : '未完成' }}
                  </a-tag>
                  <span
                    v-if="hasValidCompletionDate(formData.Data.WeeklyLastCompletionDate)"
                    class="date-hint"
                  >
                    最近完成：{{ formData.Data.WeeklyLastCompletionDate }}
                  </span>
                </div>
              </a-col>
              <a-col :span="14">
                <a-space>
                  <a-button
                    size="small"
                    :disabled="formData.Data.WeeklyCompletedThisWeek"
                    @click="markWeeklyCompleted"
                  >
                    标记完成
                  </a-button>
                  <a-button size="small" danger @click="resetWeeklyProgress"> 重置 </a-button>
                </a-space>
              </a-col>
            </a-row>
          </div>
        </a-form>
      </a-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'
import {
  useHSRPluginApi,
  type HSREngine,
  type HSRCapabilitySnapshot,
} from '@/composables/useHSRPluginApi'
import { DEFAULT_HSR_TASK_MAPPING, resolveTaskMappingValue } from '@/types/script'
import StageConfigSection from '@/views/HSRUserEdit/StageConfigSection.vue'
import type { HSRDynamicStageOptionsData, HSRUserConfigData } from '@/views/HSRUserEdit/types'
import {
  buildHSRCapabilityView,
  resolveCapabilityTaskEngine,
} from '@/views/HSRUserEdit/capabilityView'

const getCurrentISOWeek = (): string => {
  const d = new Date()
  const dayNum = d.getDay() || 7
  const thursday = new Date(d)
  thursday.setDate(d.getDate() + 4 - dayNum)
  const yearStart = new Date(thursday.getFullYear(), 0, 1)
  const weekNo = Math.ceil(((thursday.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
  return `${thursday.getFullYear()}-W${String(weekNo).padStart(2, '0')}`
}

const getCurrentDate = (): string => {
  const d = new Date()
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

const logger = window.electronAPI.getLogger('HSR 用户编辑')

const route = useRoute()
const router = useRouter()
const registryApi = useScriptRegistryApi()
const hsrPluginApi = useHSRPluginApi()
const { subscribe, unsubscribe } = useWebSocket()
const getScript = async (id: string) => (await registryApi.getScripts(id))[0] ?? null
const addUser = async (id: string) => ({ userId: (await registryApi.addUser(id)).id })
const updateUser = async (id: string, uid: string, config: Record<string, unknown>) => {
  await registryApi.updateUser(id, uid, config)
  return true
}
const getUsers = (id: string, uid: string) => registryApi.getUsers(id, uid)

const isInitializing = ref(true)
const isSaving = ref(false)
const saveError = ref('')
const sraIdDraft = ref('')
const sraPasswordDraft = ref('')
const hasStoredSraId = ref(false)
const hasStoredSraPassword = ref(false)
const sraIdPlaceholder = computed(() =>
  hasStoredSraId.value ? '已保存；输入新账号后明确保存' : '请输入账号'
)
const sraPasswordPlaceholder = computed(() =>
  hasStoredSraPassword.value ? '已保存；输入新密码后明确保存' : '请输入密码'
)

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)

const scriptName = ref('')
type HSRTaskMapping = Partial<
  Record<'Daily' | 'ReceiveRewards' | 'DivergentUniverse' | 'CurrencyWars', HSREngine>
>
type HSRScriptConfig = {
  SRA?: { Path?: string }
  M7A?: { Path?: string; LowPerformanceMode?: boolean }
  TaskMapping?: HSRTaskMapping
}
const scriptConfig = ref<HSRScriptConfig | null>(null)
const capabilitySnapshot = ref<HSRCapabilitySnapshot | null>(null)
const capabilityView = computed(() => buildHSRCapabilityView(capabilitySnapshot.value))
const effectiveEngines = computed(() => capabilityView.value.effectiveEngines)
let pluginSystemSubscriptionId: string | null = null

const handlePluginSystemMessage = (message: WebSocketBaseMessage) => {
  const payload = message.data as { kind?: string } | undefined
  if (payload?.kind !== 'snapshot') return
  void hsrPluginApi
    .getCapabilities(scriptId)
    .then(async snapshot => {
      capabilitySnapshot.value = snapshot
      await loadHsrStageOptions()
    })
    .catch(error => logger.warn(`刷新 HSR 能力失败: ${String(error)}`))
}
const hsrStageOptions = ref<HSRDynamicStageOptionsData | null>(null)
const hsrStageOptionsLoading = ref(false)
const hsrStageOptionsError = ref('')

const serverOptions = [{ value: 'CN-Official', label: '官服' }]

type WeeklyTaskMode = 'off' | 'DivergentUniverse' | 'CurrencyWars'
type MutableRecord = Record<string, unknown>

const DEFAULT_COMPLETION_DATE = '2000-01-01'

const hasValidCompletionDate = (value?: string | null): boolean => {
  const date = String(value ?? '').trim()
  return date !== '' && date !== DEFAULT_COMPLETION_DATE
}

// 根据脚本页 TaskMapping 返回指定模块的执行引擎（SRA 或 M7A）
const getTaskMapping = (
  moduleKey: 'Daily' | 'ReceiveRewards' | 'DivergentUniverse' | 'CurrencyWars'
): HSREngine | undefined => {
  const mapping: HSRTaskMapping = {
    ...DEFAULT_HSR_TASK_MAPPING,
    ...(scriptConfig.value?.TaskMapping ?? {}),
  }
  return (
    resolveCapabilityTaskEngine(capabilitySnapshot.value, moduleKey, mapping[moduleKey]) ??
    resolveTaskMappingValue(mapping[moduleKey], effectiveEngines.value)
  )
}

const dailyTaskEngine = computed(() => getTaskMapping('Daily'))

const weeklyTaskMode = computed<WeeklyTaskMode>(() => {
  if (formData.TaskSwitch.DivergentUniverse) return 'DivergentUniverse'
  if (formData.TaskSwitch.CurrencyWars) return 'CurrencyWars'
  return 'off'
})

const setWeeklyTaskMode = (mode: WeeklyTaskMode) => {
  formData.TaskSwitch.DivergentUniverse = mode === 'DivergentUniverse'
  formData.TaskSwitch.CurrencyWars = mode === 'CurrencyWars'
}

const handleWeeklyTaskModeChange = async (mode: WeeklyTaskMode) => {
  setWeeklyTaskMode(mode)
  const userData = {
    TaskSwitch: {
      DivergentUniverse: formData.TaskSwitch.DivergentUniverse,
      CurrencyWars: formData.TaskSwitch.CurrencyWars,
    },
  }

  if (isInitializing.value || isSaving.value || !userId) return
  isSaving.value = true
  saveError.value = ''
  try {
    const saved = await updateUser(scriptId, userId, userData)
    if (saved) {
      logger.info(`用户配置已保存: weeklyTaskMode=${mode}`)
    } else {
      logger.error('保存失败: weeklyTaskMode')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
    saveError.value = `周常配置保存失败：${errorMsg}`
  } finally {
    isSaving.value = false
  }
}

const loadHsrStageOptions = async () => {
  if (!scriptId || !scriptConfig.value) return
  const engine = getTaskMapping('Daily')
  if (!engine) {
    hsrStageOptions.value = null
    hsrStageOptionsError.value = ''
    hsrStageOptionsLoading.value = false
    return
  }
  hsrStageOptionsLoading.value = true
  hsrStageOptionsError.value = ''
  try {
    const pluginData = await hsrPluginApi.getStageOptions(scriptId, engine, userId || undefined)
    const data: HSRDynamicStageOptionsData = {
      engine,
      categories: pluginData.categories.map(category => ({
        categoryKey: category.key,
        categoryLabel: category.label,
        options: category.options.map(option => ({
          label: option.label,
          detail: option.detail,
          value: option.id,
          categoryKey: category.key,
          categoryLabel: category.label,
          cost: option.cost,
          maxCount: option.max_count,
          ...(option.native_payload || {}),
        })),
      })),
    }
    const optionCount = (data.categories ?? []).reduce((sum, category) => {
      return sum + (category.options?.length ?? 0)
    }, 0)
    if (!data.categories?.length || optionCount <= 0) {
      throw new Error('外部脚本未暴露可用副本选项')
    }
    hsrStageOptions.value = data
    logger.info(`HSR 体力副本动态选项加载成功: ${engine}`)
  } catch (error) {
    hsrStageOptions.value = null
    const errorMsg = error instanceof Error ? error.message : String(error)
    hsrStageOptionsError.value = `HSR 体力副本选项读取失败：${errorMsg}。请检查脚本路径或脚本版本。`
    logger.error(`HSR 体力副本动态选项加载失败: ${errorMsg}`)
  } finally {
    hsrStageOptionsLoading.value = false
  }
}

watch(
  () => scriptConfig.value?.TaskMapping?.Daily,
  () => {
    void loadHsrStageOptions()
  }
)

const currencyWarsTrailblazerName = computed(() => {
  return String(formData.Info.Name ?? '').trim() || '未设置用户名'
})

const handleTaskSwitchToggle = async (
  moduleKey: keyof HSRUserConfigData['TaskSwitch'],
  enabled: boolean
) => {
  formData.TaskSwitch[moduleKey] = enabled
  const userData: Record<string, unknown> = { TaskSwitch: { [moduleKey]: enabled } }
  if (isInitializing.value || isSaving.value || !userId) return
  isSaving.value = true
  saveError.value = ''
  try {
    const saved = await updateUser(scriptId, userId, userData)
    if (saved) {
      logger.info(`用户配置已保存: TaskSwitch.${moduleKey}=${enabled}`)
    } else {
      logger.error(`保存失败: TaskSwitch.${moduleKey}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
    saveError.value = `任务开关保存失败：${errorMsg}`
  } finally {
    isSaving.value = false
  }
}

const formData = reactive<HSRUserConfigData>({
  Info: {
    Name: '',
    Status: true,
    Server: 'CN-Official',
    RemainedDay: -1,
    Notes: '',
  },
  SRA: { Id: '', Password: '' },
  Stage: {
    Channel: 'CalyxGolden',
    ScriptStage: {},
    ScriptEchoOfWar: {},
  },
  TaskSwitch: {
    Daily: false,
    ReceiveRewards: false,
    DivergentUniverse: false,
    CurrencyWars: false,
  },
  TaskOpt: {
    EchoOfWarWeekday: 'Monday',
  },
  Data: {
    EchoOfWarCompletedThisWeek: false,
    EchoOfWarLastResetWeek: '',
    EchoOfWarLastCompletionDate: '',
    WeeklyCompletedThisWeek: false,
    WeeklyLastResetWeek: '',
    WeeklyLastCompletionDate: '',
  },
})

// EchoOfWarWeekday 变更已下沉到 StageConfigSection.vue（体力配置区）。

const eowCompletedThisWeek = computed(() => {
  return (
    !!formData.Data.EchoOfWarCompletedThisWeek &&
    formData.Data.EchoOfWarLastResetWeek === getCurrentISOWeek()
  )
})

const saveUserPatch = async (
  userData: Record<string, unknown>,
  successLog: string,
  failureLog: string
) => {
  saveError.value = ''
  try {
    const saved = await updateUser(scriptId, userId, userData)
    if (saved) {
      logger.info(successLog)
      return true
    }
    throw new Error('用户配置更新未成功')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`${failureLog}: ${errorMsg}`)
    saveError.value = `${failureLog}：${errorMsg}`
    return false
  }
}

// 历战余响 — 标记已完成
// 必须同时写入当前 ISO 周：后端 resolver 用 LastResetWeek == 当前 ISO 周
const markEowCompleted = async () => {
  const today = getCurrentDate()
  const isoWeek = getCurrentISOWeek()
  formData.Data.EchoOfWarCompletedThisWeek = true
  formData.Data.EchoOfWarLastCompletionDate = today
  formData.Data.EchoOfWarLastResetWeek = isoWeek
  await saveUserPatch(
    {
      Data: {
        EchoOfWarCompletedThisWeek: true,
        EchoOfWarLastCompletionDate: today,
        EchoOfWarLastResetWeek: isoWeek,
      },
    },
    `历战余响标记已完成 (${isoWeek})`,
    '历战余响标记已完成失败'
  )
}

// 历战余响 — 标记未完成
const resetEowProgress = async () => {
  const isoWeek = getCurrentISOWeek()
  formData.Data.EchoOfWarCompletedThisWeek = false
  formData.Data.EchoOfWarLastResetWeek = isoWeek
  formData.Data.EchoOfWarLastCompletionDate = ''
  await saveUserPatch(
    {
      Data: {
        EchoOfWarCompletedThisWeek: false,
        EchoOfWarLastResetWeek: isoWeek,
        EchoOfWarLastCompletionDate: '',
      },
    },
    `历战余响已标记未完成（${isoWeek}）`,
    '历战余响标记未完成失败'
  )
}

// 周常 — 标记完成
// 必须同时写入当前 ISO 周：后端 resolver 用 WeeklyLastResetWeek == 当前 ISO 周
// 判断 Data 是否属于本周，否则会按"新周已重置"把 done 重置为 False。
const markWeeklyCompleted = async () => {
  const today = getCurrentDate()
  const isoWeek = getCurrentISOWeek()
  formData.Data.WeeklyCompletedThisWeek = true
  formData.Data.WeeklyLastCompletionDate = today
  formData.Data.WeeklyLastResetWeek = isoWeek
  await saveUserPatch(
    {
      Data: {
        WeeklyCompletedThisWeek: true,
        WeeklyLastCompletionDate: today,
        WeeklyLastResetWeek: isoWeek,
      },
    },
    `周常标记完成 (${isoWeek})`,
    '周常标记完成失败'
  )
}

// 周常 — 重置
const resetWeeklyProgress = async () => {
  const isoWeek = getCurrentISOWeek()
  formData.Data.WeeklyCompletedThisWeek = false
  formData.Data.WeeklyLastResetWeek = isoWeek
  formData.Data.WeeklyLastCompletionDate = ''
  await saveUserPatch(
    {
      Data: {
        WeeklyCompletedThisWeek: false,
        WeeklyLastResetWeek: isoWeek,
        WeeklyLastCompletionDate: '',
      },
    },
    `周常已重置（新周：${isoWeek}）`,
    '周常重置失败'
  )
}

const handleFieldSave = async (key: string, value: unknown) => {
  const parts = key.split('.')
  let localTarget = formData as unknown as MutableRecord
  for (let i = 0; i < parts.length - 1; i++) {
    const part = parts[i]
    const next = localTarget[part]
    if (!next || typeof next !== 'object' || Array.isArray(next)) {
      localTarget[part] = {}
    }
    localTarget = localTarget[part] as MutableRecord
  }
  localTarget[parts[parts.length - 1]] = value

  if (isInitializing.value || isSaving.value || !userId) return
  isSaving.value = true
  saveError.value = ''
  try {
    const userData: MutableRecord = {}
    let current = userData
    for (let i = 0; i < parts.length - 1; i++) {
      current[parts[i]] = {}
      current = current[parts[i]] as MutableRecord
    }
    current[parts[parts.length - 1]] = value
    const saved = await updateUser(scriptId, userId, userData)
    if (saved) {
      logger.info(`用户配置已保存: ${key}`)
    } else {
      logger.error(`保存失败: ${key}`)
      saveError.value = `保存失败：${key}`
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
    saveError.value = `保存失败：${errorMsg}`
  } finally {
    isSaving.value = false
  }
}

type SraSensitiveKey = 'SRA.Id' | 'SRA.Password'

const resetSraDraft = (key: SraSensitiveKey) => {
  if (key === 'SRA.Id') {
    sraIdDraft.value = ''
  } else {
    sraPasswordDraft.value = ''
  }
}

const setStoredSraCredential = (key: SraSensitiveKey, stored: boolean) => {
  if (key === 'SRA.Id') {
    hasStoredSraId.value = stored
  } else {
    hasStoredSraPassword.value = stored
  }
}

const saveSraCredential = async (key: SraSensitiveKey, value: string) => {
  if (!value || isSaving.value || !userId) return
  isSaving.value = true
  saveError.value = ''
  try {
    const field = key === 'SRA.Id' ? 'Id' : 'Password'
    const saved = await updateUser(scriptId, userId, { SRA: { [field]: value } })
    if (saved === false) throw new Error('用户配置更新未成功')
    resetSraDraft(key)
    setStoredSraCredential(key, true)
    logger.info(`敏感字段已保存: ${key}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    saveError.value = `${key === 'SRA.Id' ? 'SRA 账号' : 'SRA 密码'}保存失败：${errorMsg}`
    logger.error(`敏感字段保存失败: ${key}: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const clearSraCredential = (key: SraSensitiveKey) => {
  const label = key === 'SRA.Id' ? 'SRA 账号' : 'SRA 密码'
  Modal.confirm({
    title: `清空${label}`,
    content: '清空后无法恢复，确定继续吗？',
    okText: '清空',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      if (isSaving.value || !userId) return
      isSaving.value = true
      saveError.value = ''
      try {
        const field = key === 'SRA.Id' ? 'Id' : 'Password'
        const saved = await updateUser(scriptId, userId, { SRA: { [field]: '' } })
        if (saved === false) throw new Error('用户配置更新未成功')
        resetSraDraft(key)
        setStoredSraCredential(key, false)
        logger.info(`敏感字段已清空: ${key}`)
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        saveError.value = `${label}清空失败：${errorMsg}`
        logger.error(`敏感字段清空失败: ${key}: ${errorMsg}`)
        throw error
      } finally {
        isSaving.value = false
      }
    },
  })
}

const handleCancel = () => router.push('/scripts')

onMounted(async () => {
  pluginSystemSubscriptionId = subscribe({ id: 'PluginSystem' }, handlePluginSystemMessage)
  if (!scriptId) {
    message.error('缺少脚本ID参数')
    handleCancel()
    return
  }
  try {
    const script = await getScript(scriptId)
    if (!script) {
      message.error('脚本不存在')
      handleCancel()
      return
    }
    if (script.type !== 'HSR' || script.editor_kind !== 'plugin:automas_script_hsr') {
      message.error('当前脚本未启用 HSR 插件编辑器')
      handleCancel()
      return
    }
    scriptName.value = script.name
    scriptConfig.value = script.config as HSRScriptConfig
    capabilitySnapshot.value = await hsrPluginApi.getCapabilities(scriptId)
    if (!isEdit.value && capabilitySnapshot.value.available === false) {
      message.warning(capabilitySnapshot.value.unavailable_reason || '请先配置可用的 HSR 引擎路径')
      handleCancel()
      return
    }
    await loadHsrStageOptions()

    if (isEdit.value) {
      await loadUserData()
    } else {
      await createUserImmediately()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
    message.error('加载脚本信息失败')
  } finally {
    isInitializing.value = false
  }
})

onUnmounted(() => {
  if (pluginSystemSubscriptionId) unsubscribe(pluginSystemSubscriptionId)
})

const createUserImmediately = async () => {
  try {
    const result = await addUser(scriptId)
    if (result && result.userId) {
      userId = result.userId
      isEdit.value = true
      router.replace({
        name: 'HSRUserEdit',
        params: { scriptId, userId: result.userId },
      })
      await loadUserData()
    } else {
      message.error('创建用户失败')
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`创建用户失败: ${errorMsg}`)
    message.error('创建用户失败')
    handleCancel()
  }
}

const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)
    if (userResponse) {
      const userData = userResponse.find(item => item.id === userId)?.config as
        | Partial<HSRUserConfigData>
        | undefined
      if (userData) {
        if (userData.Info) formData.Info = { ...formData.Info, ...userData.Info }
        if (userData.SRA) {
          hasStoredSraId.value = Boolean(userData.SRA.Id)
          hasStoredSraPassword.value = Boolean(userData.SRA.Password)
          formData.SRA = {
            ...formData.SRA,
            ...userData.SRA,
            Id: '',
            Password: '',
          }
          sraIdDraft.value = ''
          sraPasswordDraft.value = ''
        }
        if (userData.Stage) formData.Stage = { ...formData.Stage, ...userData.Stage }
        if (userData.TaskSwitch)
          formData.TaskSwitch = { ...formData.TaskSwitch, ...userData.TaskSwitch }
        if (userData.TaskOpt) formData.TaskOpt = { ...formData.TaskOpt, ...userData.TaskOpt }
        if (userData.Data) formData.Data = { ...formData.Data, ...userData.Data }
        logger.info('用户数据加载成功')
      } else {
        message.error('用户不存在')
        handleCancel()
      }
    } else {
      message.error('获取用户数据失败')
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载用户数据失败: ${errorMsg}`)
    message.error('加载用户数据失败')
  }
}
</script>

<style scoped>
.user-edit-container {
  padding: var(--v6-space-8);
  min-height: 100vh;
  background: var(--v6-color-window);
}

.user-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: var(--v6-space-4);
  max-width: 1320px;
  margin: 0 auto var(--v6-space-5);
  padding: 0 var(--v6-space-1);
}

.breadcrumb {
  margin: 0 0 var(--v6-space-2);
  font-size: var(--v6-font-size-sm);
}

.header-nav h1 {
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-3xl);
  font-weight: var(--v6-font-weight-semibold);
  line-height: var(--v6-line-height-tight);
  letter-spacing: -0.02em;
}

.page-logo {
  width: 32px;
  height: 32px;
  object-fit: contain;
}

.header-nav p {
  margin: var(--v6-space-1) 0 0;
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-base);
}

.breadcrumb-link {
  color: var(--v6-color-text-secondary);
  text-decoration: none;
}

.breadcrumb-current {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: var(--v6-font-weight-semibold);
}

.breadcrumb-logo {
  width: 18px;
  height: 18px;
  object-fit: contain;
}

.user-edit-content {
  max-width: 1320px;
  margin: 0 auto;
}

.save-error {
  margin-bottom: var(--v6-space-4);
}

.config-shell {
  display: block;
}

.config-form {
  display: block;
  max-width: none;
}

.form-section {
  min-width: 0;
  margin: 0 0 var(--v6-space-4);
  padding: var(--v6-space-5);
  background: var(--v6-vibrancy-content);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: blur(24px) saturate(1.18);
  -webkit-backdrop-filter: blur(24px) saturate(1.18);
  break-inside: avoid;
}

/* 宽容器：iPad 设置式双栏瀑布流。卡片在两列内各自纵向堆叠、互不等高拉伸；
   基本信息与体力配置（第 1 / 4 张卡）保持通栏。窄容器回落为上方的单列堆叠。 */
@container app-content (min-width: 981px) {
  .config-form {
    columns: 2;
    column-gap: var(--v6-space-4);
  }

  .form-section {
    display: inline-block;
    width: 100%;
    vertical-align: top;
  }

  .form-section:first-child,
  .form-section:nth-child(4) {
    display: block;
    column-span: all;
  }
}

/* 周常区域内的子块（差分宇宙 / 货币战争）：与主行用虚线分隔 */
.weekly-subblock {
  margin-top: var(--v6-space-4);
  padding-top: var(--v6-space-4);
  border-top: 1px dashed var(--v6-color-border-subtle);
}

.strategy-warning {
  margin-top: var(--v6-space-2);
  color: var(--v6-color-warning);
  font-weight: var(--v6-font-weight-semibold);
}

.section-header {
  margin-bottom: var(--v6-space-4);
  padding-bottom: var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.section-header h3 {
  margin: 0;
  font-size: var(--v6-font-size-xl);
  font-weight: var(--v6-font-weight-bold);
  display: flex;
  align-items: center;
  gap: var(--v6-space-3);
}

.section-header h3::before {
  display: none;
}

.form-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: var(--v6-font-weight-semibold);
  font-size: var(--v6-font-size-base);
}

.help-icon {
  color: var(--v6-color-text-tertiary);
  font-size: 13px;
}

.modern-input,
.modern-input :deep(.ant-input),
.modern-input :deep(.ant-input-number) {
  border-radius: var(--v6-radius-md);
  border: 2px solid var(--v6-color-border);
  background: var(--v6-color-surface);
}

.modern-input:focus,
.modern-input :deep(.ant-input:focus) {
  border-color: var(--v6-color-info);
  box-shadow: var(--v6-shadow-focus-ring);
}

.readonly-display {
  color: var(--v6-color-text);
  background: var(--v6-vibrancy-hover);
}

.module-checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--v6-font-size-base);
}

.cancel-button {
  border: 1px solid var(--v6-color-border);
  background: var(--v6-vibrancy-content);
  color: var(--v6-color-text);
  backdrop-filter: blur(18px) saturate(1.15);
}

.progress-group {
  display: flex;
  align-items: center;
  gap: var(--v6-space-3);
}

.progress-label {
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
  min-width: 48px;
}

.date-hint {
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text-tertiary);
  margin-left: var(--v6-space-1);
}

.sensitive-field {
  display: grid;
  gap: var(--v6-space-2);
}

.sensitive-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-2);
}

.sensitive-hint {
  color: var(--v6-color-text-tertiary);
  font-size: var(--v6-font-size-sm);
}

@media (max-width: 768px) {
  .user-edit-container {
    padding: var(--v6-space-4);
  }

  .user-edit-header {
    flex-direction: column;
    align-items: stretch;
  }

  .form-section {
    padding: var(--v6-space-4);
  }

  .form-section :deep(.ant-col) {
    flex: 0 0 100%;
    max-width: 100%;
  }

  .sensitive-actions {
    align-items: stretch;
    flex-direction: column;
  }
}

[data-perf-mode='low'] .form-section {
  background: var(--v6-color-surface);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}
</style>
