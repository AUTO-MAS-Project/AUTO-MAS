<template>
  <UserEditHeader
    :script-id="scriptId"
    :script-name="scriptName"
    :is-edit="isEdit"
    script-edit-segment="baah"
    :user-id="userId"
    @cancel="handleCancel"
  />

  <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
    <a-card class="config-card">
      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <!-- 基本信息 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('core.edit.basicInfo') }}</h3>
            <div class="section-header-actions">
              <a-button size="small" @click="openRestoreModal">
                <template #icon><HistoryOutlined /></template>
                {{ t('core.edit.configRestoreTitle') }}
              </a-button>
            </div>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <UserNameField
                name="userName"
                required
                v-model="formData.userName"
                :hint="t('core.edit.displayNameUsedIdentify')"
                :placeholder="t('core.edit.enterUsername')"
                :disabled="loading"
                enhanced
                @save="handleFieldSave('userName', formData.userName)"
              />
            </a-col>
            <a-col :span="4">
              <UserStatusField
                name="status"
                v-model="formData.Info.Status"
                :hint="t('core.edit.whetherThisUserEnabled')"
                :disabled="loading"
                @save="handleFieldSave('Info.Status', formData.Info.Status)"
              />
            </a-col>
            <a-col :span="4">
              <UserRemainedDayField
                name="remainedDay"
                v-model="formData.Info.RemainedDay"
                :hint="t('core.edit.daysLeftAccount1')"
                placeholder="-1"
                :disabled="loading"
                @save="handleFieldSave('Info.RemainedDay', formData.Info.RemainedDay)"
              />
            </a-col>
            <a-col :span="8">
              <a-form-item name="configName">
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.baahConfigName')"
                    :hint="t('core.edit.baahConfigNameHint')"
                    variant="form"
                  />
                </template>
                <a-select
                  v-model:value="formData.Info.ConfigName"
                  :placeholder="t('core.edit.baahConfigNamePlaceholder')"
                  :disabled="loading"
                  :loading="configNamesLoading"
                  :options="configNameOptions"
                  size="large"
                  show-search
                  option-filter-prop="label"
                  style="width: 100%"
                  @dropdown-visible-change="
                    (open: boolean) => {
                      if (open) void loadConfigNames()
                    }
                  "
                  @change="handleFieldSave('Info.ConfigName', formData.Info.ConfigName)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <!-- 关卡计划表与活动关优先：本次运行按它们改写 BAAH 的关卡与任务顺序 -->
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="stageMode">
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.baahStageMode')"
                    :hint="t('core.edit.baahStageModeHint')"
                    variant="form"
                  />
                </template>
                <a-select
                  v-model:value="formData.Info.StageMode"
                  :disabled="loading"
                  :options="stageModeOptions"
                  size="large"
                  style="width: 100%"
                  @change="handleFieldSave('Info.StageMode', formData.Info.StageMode)"
                />
                <a-button
                  v-if="isStagePlanMode"
                  type="link"
                  size="small"
                  class="go-plan-button"
                  @click="handleGoToPlans"
                >
                  <template #icon><CalendarOutlined /></template>
                  {{ t('core.edit.goPlan') }}
                </a-button>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item name="ifEventFirst">
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.baahIfEventFirst')"
                    :hint="t('core.edit.baahIfEventFirstHint')"
                    variant="form"
                  />
                </template>
                <a-select
                  v-model:value="formData.Info.IfEventFirst"
                  :disabled="loading"
                  size="large"
                  style="width: 100%"
                  @change="handleFieldSave('Info.IfEventFirst', formData.Info.IfEventFirst)"
                >
                  <a-select-option :value="true">{{ t('core.edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('core.edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <!-- 活动排期服务器：「活动关优先」也按它判断所选服当前有没有进行中的活动 -->
            <a-col :span="8">
              <a-form-item name="activityLineType">
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.baahActivityLineType')"
                    :hint="t('core.edit.baahActivityLineTypeHint')"
                    variant="form"
                  />
                </template>
                <a-select
                  v-model:value="formData.Info.ActivityLineType"
                  :disabled="loading"
                  size="large"
                  style="width: 100%"
                  @change="handleFieldSave('Info.ActivityLineType', formData.Info.ActivityLineType)"
                >
                  <a-select-option value="CN">
                    {{ t('core.edit.baahActivityLineCN') }}
                  </a-select-option>
                  <a-select-option value="JP">
                    {{ t('core.edit.baahActivityLineJP') }}
                  </a-select-option>
                  <a-select-option value="Globle">
                    {{ t('core.edit.baahActivityLineGloble') }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="16">
              <UserNotesField
                name="notes"
                v-model="formData.Info.Notes"
                :hint="t('core.edit.addNoteAboutThis')"
                :placeholder="t('core.edit.enterNote3')"
                :disabled="loading"
                :rows="3"
                enhanced
                @save="handleFieldSave('Info.Notes', formData.Info.Notes)"
              />
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.baahUserTag')"
                    :hint="t('core.edit.baahUserTagHint')"
                    variant="form"
                  />
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
              <GeneralConfigModeSelector
                :model-value="formData.Info.Base"
                :options="baahConfigModeOptions"
                :disabled="loading"
                :alert-message="t('core.edit.configSourceHintBase')"
                @change="handleConfigModeChange"
              />
            </a-col>
          </a-row>
        </div>

        <!-- 数据统计（只读，由本软件自动写入） -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('core.edit.statistics') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.baahLastProxyDate')"
                    :hint="t('core.edit.baahDataReadOnlyHint')"
                    variant="form"
                  />
                </template>
                <a-input
                  :value="formatConfigDate(formData.Data.LastProxyDate, 4 * 60)"
                  readonly
                  size="large"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.baahProxyTimes')"
                    :hint="t('core.edit.baahDataReadOnlyHint')"
                    variant="form"
                  />
                </template>
                <a-input :value="formData.Data.ProxyTimes" readonly size="large" />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <UserNotifyConfig v-model="formData.Notify" :loading="loading" @save="handleFieldSave" />
      </a-form>
    </a-card>
  </ConfigLockPanel>

  <!-- ══ 配置恢复（通用组件：MAS 用户字段在前、BAAH 原生配置在后）══ -->
  <ConfigRestoreSection
    v-model:open="restoreOpen"
    :disabled="configLocked"
    :script-name="BAAH_DISPLAY_NAME"
    :targets="restoreTargets"
    :api="restoreApi"
    :user-desc="t('core.edit.baahConfigRestoreUserDesc')"
    :script-desc="t('core.edit.baahConfigRestoreScriptDesc')"
    :on-restored="handleRestored"
  >
    <!-- mas 备份为字段侧车分区、native 备份为关键字段反读分区 -->
    <template #preview="{ raw }">
      <NoData
        v-if="!previewSections(raw).length"
        :description="t('core.edit.configRestorePreviewEmpty')"
      />
      <div v-else>
        <template v-for="s in previewSections(raw)" :key="s.name">
          <h4 class="baah-preview-title">{{ s.label }}</h4>
          <a-descriptions
            v-if="s.rows && s.rows.length"
            :column="1"
            size="small"
            bordered
            class="baah-preview-box"
          >
            <a-descriptions-item v-for="row in s.rows" :key="row.key" :label="row.key">
              {{ row.value }}
            </a-descriptions-item>
          </a-descriptions>
          <div v-for="g in s.groups ?? []" :key="`${s.name}-${g.name}`" class="baah-preview-group">
            <div class="baah-preview-group-name">{{ g.name }}</div>
            <a-descriptions :column="1" size="small" bordered class="baah-preview-box">
              <a-descriptions-item v-for="row in g.rows" :key="row.key" :label="row.key">
                {{ row.value }}
              </a-descriptions-item>
            </a-descriptions>
          </div>
        </template>
      </div>
    </template>
  </ConfigRestoreSection>
</template>

<script setup lang="ts">
import UserNameField from '@/views/EditView/User/components/UserNameField.vue'
import UserNotesField from '@/views/EditView/User/components/UserNotesField.vue'
import UserRemainedDayField from '@/views/EditView/User/components/UserRemainedDayField.vue'
import UserStatusField from '@/views/EditView/User/components/UserStatusField.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { formatConfigDate } from '@/utils/configDateTime'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import UserEditHeader from '@/components/UserEditHeader.vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { useI18n } from 'vue-i18n'
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { CalendarOutlined, HistoryOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { parseStatusTagList } from '@/composables/useStatusTag.ts'
import { Service } from '@/api'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import GeneralConfigModeSelector from '@/views/EditView/User/GeneralConfigModeSelector.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import { BaahService, type ComboBoxItem } from '@/api'
import { PlanComboxIn } from '@/api/models/PlanComboxIn'
import { navigateTo } from '@/router'
import { useConfigBackupApi } from '@/composables/useConfigBackupApi'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('BAAH用户编辑')

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading, error: userApiError } = useUserApi()
const { getScript, error: scriptApiError } = useScriptApi()

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

// BAAH 用户默认数据（与后端 BAAHUserConfig 的默认值保持一致）
const getDefaultBAAHUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    Base: 'independent',
    RemainedDay: -1,
    ConfigName: '',
    // Fixed 表示按 BAAH 自己的关卡配置运行，其余取值是关卡计划表 uid
    StageMode: 'Fixed',
    ActivityLineType: 'CN',
    IfEventFirst: false,
    Notes: '',
    Tag: '',
  },
  Data: {
    LastProxyDate: '2000-01-01T00:00:00+04:00',
    ProxyTimes: 0,
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

// 创建扁平化的表单数据，用于表单验证
const formData = reactive({
  // 扁平化的验证字段
  userName: '',
  // 嵌套的实际数据
  ...getDefaultBAAHUserData(),
})

// 配置名下拉候选：由后端按主程序路径实时读取 BAAH_CONFIGS，两份配置名共用
const configNameOptions = ref<{ label: string; value: string }[]>([])
const configNamesLoading = ref(false)
const loadConfigNames = async () => {
  configNamesLoading.value = true
  try {
    const resp = await BaahService.getBaahConfigNamesApiApiScriptsBaahConfigNamesGet(scriptId)
    configNameOptions.value = (resp.data || [])
      .filter((item): item is ComboBoxItem & { value: string } => item.value != null)
      .map(item => ({ label: item.label, value: item.value }))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  } finally {
    configNamesLoading.value = false
  }
}

// 关卡计划表下拉候选：后端按消费方 baah 返回 BAAH 计划表；「固定」始终排在第一项
// 用本地词表的固定项，保证在英文/日文界面下也是自己的语言
const stageModeOptions = ref<Array<{ label: string; value: string }>>([
  { label: t('core.edit.fixed'), value: 'Fixed' },
])
const isStagePlanMode = computed(() => formData.Info.StageMode !== 'Fixed')
const loadStageModeOptions = async () => {
  try {
    const response = await Service.getPlanComboxApiInfoComboxPlanPost({
      consumer: PlanComboxIn.consumer.BAAH,
    })
    if (response?.code === 200 && response.data) {
      const planOptions = response.data
        .filter((item): item is ComboBoxItem & { value: string } => item.value !== null)
        .filter(item => item.value !== 'Fixed')
        .map(item => ({ label: item.label, value: item.value }))
      stageModeOptions.value = [{ label: t('core.edit.fixed'), value: 'Fixed' }, ...planOptions]
    }
  } catch (error) {
    logger.error(`加载关卡计划表失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}

// 只读标签：后端按运行情况生成的 JSON 字符串
const userTags = computed(() => parseStatusTagList(formData.Info.Tag))

// 表单验证规则
const rules = computed(() => {
  const baseRules: Record<string, Rule[]> = {
    userName: [
      { required: true, message: t('core.edit.enterUsername'), trigger: 'blur' },
      { min: 1, max: 50, message: t('core.edit.usernameMustBe1'), trigger: 'blur' },
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

// 配置来源两态卡片（value 为后端 Info.Base 取值，驱动逻辑需保持原样；文案走词表）
// 「共享」置灰：BAAH 运行始终按用户独立配置注入（任务模块不消费 Info.Base），
// 选了也不生效——禁用并悬停说明原因
const baahConfigModeOptions: Array<{
  label: string
  value: 'shared' | 'independent' | 'native'
  title: string
  description: string
  icon: 'database' | 'setting'
  disabled?: boolean
  disabledReason?: string
}> = [
  {
    label: t('core.edit.script'),
    value: 'shared',
    title: t('core.edit.script'),
    description: t('core.edit.useScriptS'),
    icon: 'database',
    disabled: true,
    disabledReason: t('core.edit.scriptModeDisabled'),
  },
  {
    label: t('core.edit.user'),
    value: 'independent',
    title: t('core.edit.user'),
    description: t('core.edit.useThisUserS'),
    icon: 'database',
  },
  {
    label: t('core.edit.directControl'),
    value: 'native',
    title: t('core.edit.directControl'),
    description: t('core.edit.nativeConfigSourceDescription'),
    icon: 'setting',
  },
]

// 配置来源切换：校验 value ∈ options → 赋值 Info.Base → 保存
const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['shared', 'independent', 'native'].includes(value)) return
  formData.Info.Base = value as 'shared' | 'independent' | 'native'
  await handleFieldSave('Info.Base', formData.Info.Base)
}

// 直接跳到当前选中的关卡计划表，省去在计划管理里再找一遍
const handleGoToPlans = () => {
  navigateTo('/plans', { query: { planId: formData.Info.StageMode } })
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

    if (!(await updateUser(scriptId, userId, userData))) return
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
      if (!scriptApiError.value) message.error(t('core.edit.scriptDoesNotExist2'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
    if (!scriptApiError.value) message.error(t('core.edit.couldNotLoadScript2'))
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
      if (!userApiError.value) message.error(t('core.edit.couldNotCreateUser'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`创建用户失败: ${errorMsg}`)
    if (!userApiError.value) message.error(t('core.edit.couldNotCreateUser'))
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

        // 填充 BAAH 用户数据
        if (userIndex.type === 'BAAHUserConfig') {
          Object.assign(formData, {
            Info: { ...getDefaultBAAHUserData().Info, ...userData.Info },
            Notify: { ...getDefaultBAAHUserData().Notify, ...userData.Notify },
            Data: { ...getDefaultBAAHUserData().Data, ...userData.Data },
          })
        }

        // 同步扁平化字段 - 使用nextTick确保数据更新完成后再同步
        await nextTick()
        formData.userName = formData.Info.Name || ''

        logger.info('用户数据加载成功')

        // 数据加载完成，允许自动保存
        isInitializing.value = false
      } else {
        message.error(t('core.edit.userDoesNotExist'))
        handleCancel()
      }
    } else {
      if (!userApiError.value) message.error(t('core.edit.couldNotFetchUser'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载用户数据失败: ${errorMsg}`)
    if (!userApiError.value) message.error(t('core.edit.couldNotLoadUser2'))
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

// ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
// 专项统一名（文案参数化用）：BAAH 统一叫「baah」
const BAAH_DISPLAY_NAME = 'baah'
const restoreOpen = ref(false)

// 目标池顺序 = segmented 展示顺序：MAS 用户字段（在前）、BAAH 原生配置（在后）
const restoreTargets: Array<{ key: string; kind: 'user' | 'script' }> = [
  { key: 'mas', kind: 'user' },
  { key: 'native', kind: 'script' },
]

// 组件调用后端：通用 /backup/* 端点（脚本/用户上下文在此闭包捕获）
const { restoreApi, ensureBackup } = useConfigBackupApi({
  scriptId,
  userId: () => userId,
  logger,
})

const openRestoreModal = () => {
  restoreOpen.value = true
}

// 预览响应原文（unknown）收敛为分区视图：泛用组件的 raw 插槽不带专项类型
interface BAAHPreviewRow {
  key: string
  value: string
}
interface BAAHPreviewSection {
  name: string
  label: string
  rows?: BAAHPreviewRow[]
  groups?: Array<{ name: string; rows: BAAHPreviewRow[] }>
}
const previewSections = (raw: unknown): BAAHPreviewSection[] =>
  (raw as { sections?: BAAHPreviewSection[] } | null)?.sections ?? []

// 一键恢复成功：mas 恢复回填字段（当前仅 ConfigName），native 恢复写
// BAAH 配置文件——ConfigName 未变无需刷新表单
const handleRestored = async (target: string) => {
  restoreOpen.value = false
  if (target === 'mas') {
    isInitializing.value = true
    try {
      await loadUserData()
    } finally {
      // 加载失败也要复位：否则按钮永久转圈
      isInitializing.value = false
    }
  }
}

// 编辑界面归档（进入/退出时机，指纹去重）：进入归档 BAAH 原生配置当前状态
// （用户可能刚在 BAAH jsoneditor 里改过），退出归档 MAS 编辑页字段终态；
// 运行前归档挂在 AutoProxy.prepare（托管写入前）
const ensureBAAHBackup = ensureBackup

onMounted(async () => {
  if (!scriptId) {
    message.error(t('core.edit.missingScriptIdParameter'))
    handleCancel()
    return
  }

  // 先等脚本信息与用户就绪（新建模式内部会创建用户并写入 userId）再归档，
  // 否则新建用户首次进入会因 userId 未就绪静默跳过归档
  await loadScriptInfo()
  await loadStageModeOptions()
  await nextTick()
  void ensureBAAHBackup('native')
})

onUnmounted(() => {
  // 退出编辑页：归档 MAS 编辑页字段终态（BAAH 无遮罩会话，无需停会话）
  void ensureBAAHBackup('mas')
})
</script>

<style scoped>
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
}

/* ══ 配置恢复预览（分区标题 + 表格 + 详情分组）══ */
.baah-preview-title {
  margin: 16px 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.baah-preview-title:first-of-type {
  margin-top: 0;
}

.baah-preview-group {
  margin-top: 12px;
}

.baah-preview-group-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
  margin-bottom: 4px;
}

.baah-preview-box {
  width: 100%;
}

.user-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  min-height: 40px;
}

.go-plan-button {
  padding-inline: 0;
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
  .user-edit-content {
    max-width: 100%;
  }
}
</style>
