<template>
  <div class="user-edit-container">
    <div class="user-edit-header">
      <div class="header-nav">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts" class="breadcrumb-link"> 脚本管理</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>{{ scriptName }}</a-breadcrumb-item>
          <a-breadcrumb-item>
            <span class="breadcrumb-current">
              <img src="../../../assets/hsr.png" alt="HSR" class="breadcrumb-logo" />
              {{ isEdit ? '编辑 HSR 用户' : '添加 HSR 用户' }}
            </span>
          </a-breadcrumb-item>
        </a-breadcrumb>
      </div>
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
    </div>

    <div class="user-edit-content">
      <a-card class="config-card">
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
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">账号</span>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Id"
                    placeholder="请输入账号"
                    size="large"
                    class="modern-input"
                    @blur="handleFieldSave('Info.Id', formData.Info.Id)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">密码</span>
                  </template>
                  <!-- 用 input-class 把 modern-input 挂到内部 <input>，避免 a-input-password 外层嵌套 div -->
                  <a-input-password
                    v-model:value="formData.Info.Password"
                    placeholder="请输入密码"
                    size="large"
                    :input-class="'modern-input'"
                    @blur="handleFieldSave('Info.Password', formData.Info.Password)"
                  />
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

          <!-- 周常/月常：三深渊（每月一次，三个一起执行）+ 周常（差分宇宙/货币战争）-->
          <div class="form-section">
            <div class="section-header"><h3>周常/月常</h3></div>
            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item label="三深渊（每月一次，三个一起执行）">
                  <a-tooltip title="前面的功能，以后再来探索吧~">
                    <a-switch
                      :checked="false"
                      checked-children="开启"
                      un-checked-children="关闭"
                      disabled
                    />
                  </a-tooltip>
                  <div
                    class="form-item-hint"
                    style="color: var(--ant-color-text-tertiary); margin-top: 4px"
                  >
                    前面的功能，以后再来探索吧~
                  </div>
                </a-form-item>
              </a-col>
              <a-col :span="12">
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
              </a-col>
            </a-row>

            <!-- 三深渊子区域（开关开启时显示）：语义说明 + 导入按钮 + 三份快照摘要 -->
            <div v-if="formData.TaskSwitch.ForgottenHall" class="weekly-subblock">
              <a-alert type="info" show-icon>
                <template #message>
                  <div>
                    开启三深渊后，会按已导入的三份快照依次执行：混沌回忆 → 虚构叙事 →
                    末日幻影，每月执行一次。
                  </div>
                  <div>
                    请先在 M7A 配好三深渊（关卡范围与队伍），再点击下方「从 M7A
                    导入三深渊配置」导入三份快照。
                  </div>
                </template>
              </a-alert>
              <a-alert
                v-if="abyssCompletedThisMonth"
                type="success"
                show-icon
                style="margin-top: 8px"
                message="三深渊本月已完成，本月不会再执行；如需重跑请在下方「进度与重置」重置三深渊本月进度。"
              />
              <a-alert
                v-else-if="!abyssSnapshotsReady"
                type="warning"
                show-icon
                style="margin-top: 8px"
                message="尚未导入完整的三深渊快照（混沌回忆 / 虚构叙事 / 末日幻影）。请先从 M7A 导入；缺任一快照时三深渊不会执行并会清晰报错。"
              />
              <AbyssConfigSection
                :form-data="formData"
                :loading="isSaving"
                :script-config="scriptConfig"
                :script-id="scriptId"
                :user-id="userId"
                @imported="handleAbyssImported"
              />
            </div>

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
                message="请先在脚本页 TaskMapping 选择 SRA 或 三月七"
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
                  <div>- 运行次数 2</div>
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
                message="请先在脚本页 TaskMapping 选择 SRA 或 三月七"
              />
            </div>
          </div>

          <!-- 关卡配置 -->
          <StageConfigSection
            :form-data="formData"
            :loading="isSaving"
            :daily-engine="getTaskMapping('Daily')"
            :stage-options="hsrStageOptions"
            :stage-options-loading="hsrStageOptionsLoading"
            :stage-options-error="hsrStageOptionsError"
            @save="handleFieldSave"
          />

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

            <!-- 三深渊本月进度（每月一次；后端本月已完成会自动跳过三深渊） -->
            <a-row :gutter="24" align="middle" style="margin-top: 16px">
              <a-col :span="10">
                <div class="progress-group">
                  <span class="progress-label">三深渊</span>
                  <a-tag :color="abyssCompletedThisMonth ? 'green' : 'orange'">
                    本月 {{ abyssCompletedThisMonth ? '已完成' : '未完成' }}
                  </a-tag>
                  <span
                    v-if="hasValidCompletionDate(formData.Data.AbyssLastCompletionDate)"
                    class="date-hint"
                  >
                    最近完成：{{ formData.Data.AbyssLastCompletionDate }}
                  </span>
                </div>
              </a-col>
              <a-col :span="14">
                <a-space>
                  <a-button
                    size="small"
                    :disabled="abyssCompletedThisMonth"
                    @click="markAbyssCompleted"
                  >
                    标记完成
                  </a-button>
                  <a-button size="small" danger @click="resetAbyssProgress"> 重置 </a-button>
                </a-space>
              </a-col>
            </a-row>
          </div>
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import type { AbyssSnapshotImportOut, HSRConfig_TaskMapping, HSRUserConfig_TaskSwitch } from '@/api'
import { DEFAULT_HSR_TASK_MAPPING, resolveTaskMappingValue } from '@/types/script'
import type { HSRScriptConfig } from '@/types/script'
import StageConfigSection from '@/views/HSRUserEdit/StageConfigSection.vue'
import AbyssConfigSection from '@/views/HSRUserEdit/AbyssConfigSection.vue'
import { parseAbyssSnapshots } from '@/views/HSRUserEdit/snapshot'
import type { HSRAbyssKey } from '@/views/HSRUserEdit/snapshot'
import type {
  HSRDynamicStageOptionsData,
  HSRUserConfigAbyss,
  HSRUserConfigData,
} from '@/views/HSRUserEdit/types'

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

const getCurrentMonth = (): string => {
  const d = new Date()
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  return `${yyyy}-${mm}`
}

const logger = window.electronAPI.getLogger('HSR 用户编辑')

const route = useRoute()
const router = useRouter()
const { addUser, updateUser, getUsers } = useUserApi()
const { getScript, getHsrStageOptions } = useScriptApi()

const isInitializing = ref(true)
const isSaving = ref(false)

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)

const scriptName = ref('')
const scriptConfig = ref<HSRScriptConfig | null>(null)
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
): 'SRA' | 'M7A' => {
  const mapping: HSRConfig_TaskMapping = {
    ...DEFAULT_HSR_TASK_MAPPING,
    ...(scriptConfig.value?.TaskMapping ?? {}),
  }
  return resolveTaskMappingValue(mapping[moduleKey], new Set(['M7A', 'SRA'])) ?? 'M7A'
}

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
  } finally {
    isSaving.value = false
  }
}

const loadHsrStageOptions = async () => {
  if (!scriptId || !scriptConfig.value) return
  const engine = getTaskMapping('Daily')
  hsrStageOptionsLoading.value = true
  hsrStageOptionsError.value = ''
  try {
    const data = await getHsrStageOptions(scriptId, engine)
    if (!data) throw new Error('接口未返回副本选项')
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

const ABYSS_DEFS: { key: HSRAbyssKey }[] = [
  { key: 'ForgottenHall' },
  { key: 'PureFiction' },
  { key: 'Apocalyptic' },
]

const isNonEmptyObject = (value: unknown): value is Record<string, unknown> => {
  return (
    !!value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length > 0
  )
}

// 三深渊开关开启时会一次执行三份快照，缺任一快照后端会清晰报错。
const abyssSnapshotsReady = computed<boolean>(() => {
  const snapshots = parseAbyssSnapshots(formData.Abyss?.Snapshots)
  return ABYSS_DEFS.every(def => isNonEmptyObject(snapshots[def.key]))
})

// 三深渊本月是否已完成（跨月内存重置：与后端 _resolve_abyss_monthly_skip 对齐）。
// 仅当 AbyssLastResetMonth == 当前自然月 且 AbyssCompletedThisMonth 为真才算"本月已完成"。
const abyssCompletedThisMonth = computed<boolean>(() => {
  const data = formData.Data
  if (!data?.AbyssCompletedThisMonth) return false
  return (data.AbyssLastResetMonth ?? '') === getCurrentMonth()
})

const handleTaskSwitchToggle = async (
  moduleKey: keyof HSRUserConfig_TaskSwitch,
  enabled: boolean
) => {
  formData.TaskSwitch[moduleKey] = enabled
  const userData: Record<string, unknown> = { TaskSwitch: { [moduleKey]: enabled } }
  if (isInitializing.value || isSaving.value || !userId) return
  isSaving.value = true
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
  } finally {
    isSaving.value = false
  }
}

const formData = reactive<HSRUserConfigData>({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    Server: 'CN-Official',
    RemainedDay: -1,
    Notes: '',
  },
  Stage: {
    Channel: 'CalyxGolden',
    ScriptStage: '{ }',
    ScriptEchoOfWar: '{ }',
  },
  TaskSwitch: {
    Daily: false,
    ReceiveRewards: false,
    DivergentUniverse: false,
    CurrencyWars: false,
    ForgottenHall: false,
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
    AbyssCompletedThisMonth: false,
    AbyssLastResetMonth: '',
    AbyssLastCompletionDate: '',
  },
  Abyss: {
    Snapshots: '{}',
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
  const saved = await updateUser(scriptId, userId, userData)
  if (saved) {
    logger.info(successLog)
  } else {
    logger.error(failureLog)
  }
  return saved
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

// 三深渊 — 标记本月完成
// 同时写入当前自然月：后端 _resolve_abyss_monthly_skip 用 AbyssLastResetMonth ==
// 当前自然月 判断 Data 是否属于本月，否则会按"新月已重置"重新算未完成。
const markAbyssCompleted = async () => {
  const today = getCurrentDate()
  const month = getCurrentMonth()
  formData.Data.AbyssCompletedThisMonth = true
  formData.Data.AbyssLastCompletionDate = today
  formData.Data.AbyssLastResetMonth = month
  await saveUserPatch(
    {
      Data: {
        AbyssCompletedThisMonth: true,
        AbyssLastCompletionDate: today,
        AbyssLastResetMonth: month,
      },
    },
    `三深渊标记本月完成 (${month})`,
    '三深渊标记本月完成失败'
  )
}

// 三深渊 — 重置本月进度
const resetAbyssProgress = async () => {
  const month = getCurrentMonth()
  formData.Data.AbyssCompletedThisMonth = false
  formData.Data.AbyssLastResetMonth = month
  formData.Data.AbyssLastCompletionDate = ''
  await saveUserPatch(
    {
      Data: {
        AbyssCompletedThisMonth: false,
        AbyssLastResetMonth: month,
        AbyssLastCompletionDate: '',
      },
    },
    `三深渊本月进度已重置（${month}）`,
    '三深渊本月进度重置失败'
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
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const handleCancel = () => router.push('/scripts')

// 三深渊快照导入后回调：由父页面统一同步本地表单状态。
const handleAbyssImported = (response: AbyssSnapshotImportOut) => {
  const updated = response?.updatedUserData
  if (updated?.Abyss) {
    formData.Abyss = {
      Snapshots: (updated.Abyss as HSRUserConfigAbyss).Snapshots ?? '{}',
    }
  }
  logger.info('三深渊快照导入完成')
}

onMounted(async () => {
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
    scriptName.value = script.name
    scriptConfig.value = script.config as HSRScriptConfig
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
    if (userResponse && userResponse.code === 200) {
      const users = userResponse.data as Record<string, Partial<HSRUserConfigData> | undefined>
      const userData = users?.[userId]
      if (userData) {
        if (userData.Info) formData.Info = { ...formData.Info, ...userData.Info }
        if (userData.Stage) formData.Stage = { ...formData.Stage, ...userData.Stage }
        if (userData.TaskSwitch)
          formData.TaskSwitch = { ...formData.TaskSwitch, ...userData.TaskSwitch }
        if (userData.TaskOpt) formData.TaskOpt = { ...formData.TaskOpt, ...userData.TaskOpt }
        if (userData.Data) formData.Data = { ...formData.Data, ...userData.Data }
        if (userData.Abyss) formData.Abyss = { ...formData.Abyss, ...userData.Abyss }
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
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

.user-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding: 0 8px;
}

.breadcrumb {
  margin: 0;
}

.breadcrumb-link {
  color: var(--ant-color-text-secondary);
  text-decoration: none;
}

.breadcrumb-current {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}

.breadcrumb-logo {
  width: 18px;
  height: 18px;
  object-fit: contain;
}

.user-edit-content {
  max-width: 1400px;
  margin: 0 auto;
}

.config-card {
  border-radius: 12px;
  box-shadow: none;
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.config-form {
  max-width: none;
}

.form-section {
  margin-bottom: 12px;
  padding: 20px 24px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
}

/* 周常/月常区域内的子块（三深渊 / 差分宇宙 / 货币战争）：与主行用虚线分隔 */
.weekly-subblock {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed var(--ant-color-border-secondary);
}

.strategy-warning {
  margin-top: 8px;
  color: var(--ant-color-warning);
  font-weight: 600;
}

.section-header {
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 22px;
  background: var(--ant-color-primary);
  border-radius: 2px;
}

.form-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.modern-input,
.modern-input :deep(.ant-input),
.modern-input :deep(.ant-input-number) {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
}

.modern-input:focus,
.modern-input :deep(.ant-input:focus) {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px var(--ant-color-primary-bg);
}

.readonly-display {
  color: var(--ant-color-text);
  background: var(--ant-color-fill-quaternary);
}

.module-checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.cancel-button {
  height: 40px;
}

.progress-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.progress-label {
  font-weight: 600;
  color: var(--ant-color-text);
  min-width: 48px;
}

.date-hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  margin-left: 4px;
}
</style>
