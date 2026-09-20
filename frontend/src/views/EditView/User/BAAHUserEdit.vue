<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit/baah`" class="breadcrumb-link">
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
            <div class="section-header-actions">
              <a-button size="small" @click="openRestoreModal">
                <template #icon><HistoryOutlined /></template>
                {{ t('edit.configRestoreTitle') }}
              </a-button>
            </div>
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
              <a-form-item name="configName">
                <template #label>
                  <a-tooltip :title="t('edit.baahConfigNameHint')">
                    <span class="form-label">
                      {{ t('edit.baahConfigName') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="formData.Info.ConfigName"
                  :placeholder="t('edit.baahConfigNamePlaceholder')"
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

          <!-- 活动适配：按碧蓝档案当前有没有活动，改用另一份配置文件 -->
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="ifActivityAdapt">
                <template #label>
                  <a-tooltip :title="t('edit.baahIfActivityAdaptHint')">
                    <span class="form-label">
                      {{ t('edit.baahIfActivityAdapt') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="formData.Info.IfActivityAdapt"
                  :disabled="loading"
                  size="large"
                  style="width: 100%"
                  @change="
                    handleFieldSave('Info.IfActivityAdapt', formData.Info.IfActivityAdapt)
                  "
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item name="activityLineType">
                <template #label>
                  <a-tooltip :title="t('edit.baahActivityLineTypeHint')">
                    <span class="form-label">
                      {{ t('edit.baahActivityLineType') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="formData.Info.ActivityLineType"
                  :disabled="loading || !formData.Info.IfActivityAdapt"
                  size="large"
                  style="width: 100%"
                  @change="
                    handleFieldSave('Info.ActivityLineType', formData.Info.ActivityLineType)
                  "
                >
                  <a-select-option value="CN">
                    {{ t('edit.baahActivityLineCN') }}
                  </a-select-option>
                  <a-select-option value="JP">
                    {{ t('edit.baahActivityLineJP') }}
                  </a-select-option>
                  <a-select-option value="Globle">
                    {{ t('edit.baahActivityLineGloble') }}
                  </a-select-option>
                </a-select>
                <div v-if="formData.Info.IfActivityAdapt" class="activity-status">
                  <a-spin v-if="activityStatusLoading" size="small" />
                  <template v-else-if="activityStatus">
                    <template v-if="activityStatus.Running">
                      <span class="activity-status-label">
                        {{ t('edit.baahActivityRunning') }}
                      </span>
                      <span class="activity-status-name">{{ activityStatus.Name }}</span>
                      <div class="activity-status-time">
                        {{ activityStatus.StartTime }} ~ {{ activityStatus.EndTime }}
                      </div>
                    </template>
                    <template v-else-if="activityStatus.NextName">
                      <span class="activity-status-label">
                        {{ t('edit.baahActivityUpcoming') }}
                      </span>
                      <span class="activity-status-name">{{ activityStatus.NextName }}</span>
                      <div class="activity-status-time">{{ activityStatus.NextStartTime }}</div>
                    </template>
                    <div v-else class="activity-status-empty">
                      {{ t('edit.baahActivityNone') }}
                    </div>
                  </template>
                  <div v-else class="activity-status-empty">
                    {{ t('edit.baahActivityUnavailable') }}
                  </div>
                </div>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item name="activityConfigName">
                <template #label>
                  <a-tooltip :title="t('edit.baahActivityConfigNameHint')">
                    <span class="form-label">
                      {{ t('edit.baahActivityConfigName') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="formData.Info.ActivityConfigName"
                  :placeholder="t('edit.baahActivityConfigNamePlaceholder')"
                  :disabled="loading || !formData.Info.IfActivityAdapt"
                  :loading="configNamesLoading"
                  :options="configNameOptions"
                  size="large"
                  show-search
                  allow-clear
                  option-filter-prop="label"
                  style="width: 100%"
                  @dropdown-visible-change="
                    (open: boolean) => {
                      if (open) void loadConfigNames()
                    }
                  "
                  @change="
                    handleFieldSave(
                      'Info.ActivityConfigName',
                      formData.Info.ActivityConfigName ?? ''
                    )
                  "
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="16">
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
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.baahUserTagHint')">
                    <span class="form-label">
                      {{ t('edit.baahUserTag') }}
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
              <GeneralConfigModeSelector
                :model-value="formData.Info.Mode"
                :options="baahConfigModeOptions"
                :disabled="loading"
                :alert-message="t('edit.configSourceHintBase')"
                @change="handleConfigModeChange"
              />
            </a-col>
          </a-row>
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
                    {{ t('edit.baahLastProxyDate') }}
                    <a-tooltip :title="t('edit.baahDataReadOnlyHint')">
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
                    {{ t('edit.baahProxyTimes') }}
                    <a-tooltip :title="t('edit.baahDataReadOnlyHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
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
      :user-desc="t('edit.baahConfigRestoreUserDesc')"
      :script-desc="t('edit.baahConfigRestoreScriptDesc')"
      :on-restored="handleRestored"
    >
      <!-- mas 备份为字段侧车分区、native 备份为关键字段反读分区 -->
      <template #preview="{ raw }">
        <a-empty
          v-if="!previewSections(raw).length"
          :description="t('edit.configRestorePreviewEmpty')"
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
            <div
              v-for="g in s.groups ?? []"
              :key="`${s.name}-${g.name}`"
              class="baah-preview-group"
            >
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
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { useI18n } from 'vue-i18n'
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, HistoryOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { parseStatusTagList } from '@/composables/useStatusTag.ts'
import { Service } from '@/api'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import GeneralConfigModeSelector from '@/views/EditView/User/GeneralConfigModeSelector.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import { BaahService, type BlueArchiveActivityStatusOut, type ComboBoxItem } from '@/api'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('BAAH用户编辑')

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

// BAAH 用户默认数据（与后端 BAAHUserConfig 的默认值保持一致）
const getDefaultBAAHUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    Mode: '用户',
    RemainedDay: -1,
    ConfigName: '',
    ActivityConfigName: '',
    IfActivityAdapt: false,
    ActivityLineType: 'CN',
    Notes: '',
    Tag: '',
  },
  Data: {
    LastProxyDate: '2000-01-01',
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

// 所选服的活动排期，开关或服务器变化时重新取
const activityStatus = ref<BlueArchiveActivityStatusOut | null>(null)
const activityStatusLoading = ref(false)
// 快速切换服务器时先发的请求可能后到：用代数标记，只采纳最新一次的结果
let activityStatusGeneration = 0
const loadActivityStatus = async () => {
  if (!formData.Info.IfActivityAdapt) {
    activityStatusGeneration += 1
    activityStatus.value = null
    activityStatusLoading.value = false
    return
  }

  const generation = (activityStatusGeneration += 1)
  activityStatusLoading.value = true
  try {
    // 服务器值缺失时兜底成国服，避免拼出 lineType=null 的请求被后端拒掉
    const lineType = (formData.Info.ActivityLineType || 'CN') as 'JP' | 'Globle' | 'CN'
    const resp =
      await BaahService.getBaahActivityStatusApiApiScriptsBaahActivityStatusGet(lineType)
    if (generation !== activityStatusGeneration) return
    activityStatus.value = resp
  } catch (e) {
    if (generation !== activityStatusGeneration) return
    logger.error(e instanceof Error ? e.message : String(e))
    activityStatus.value = null
  } finally {
    if (generation === activityStatusGeneration) {
      activityStatusLoading.value = false
    }
  }
}

watch(
  () => [formData.Info.IfActivityAdapt, formData.Info.ActivityLineType],
  () => {
    void loadActivityStatus()
  },
  { immediate: true }
)

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

// 配置来源两态卡片（value 为后端 Info.Mode 取值，驱动逻辑需保持原样；文案走词表）
// 「脚本」置灰：BAAH 运行始终按用户独立配置注入（任务模块不消费 Info.Mode），
// 选了也不生效——禁用并悬停说明原因
const baahConfigModeOptions: Array<{
  label: string
  value: '脚本' | '用户' | '直控'
  title: string
  description: string
  icon: 'database' | 'setting'
  disabled?: boolean
  disabledReason?: string
}> = [
  {
    label: t('edit.script'),
    value: '脚本',
    title: t('edit.script'),
    description: t('edit.useScriptS'),
    icon: 'database',
    disabled: true,
    disabledReason: t('edit.scriptModeDisabled'),
  },
  {
    label: t('edit.user'),
    value: '用户',
    title: t('edit.user'),
    description: t('edit.useThisUserS'),
    icon: 'database',
  },
  {
    label: t('edit.directControl'),
    value: '直控',
    title: t('edit.directControl'),
    description: t('edit.nativeConfigSourceDescription'),
    icon: 'setting',
  },
]

// 配置来源切换：校验 value ∈ options → 赋值 Info.Mode → 保存
const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['脚本', '用户', '直控'].includes(value)) return
  formData.Info.Mode = value as '脚本' | '用户' | '直控'
  await handleFieldSave('Info.Mode', formData.Info.Mode)
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
const restoreApi = {
  list: async (target: string) =>
    Service.listConfigBackupsApiApiScriptsBackupListGet(scriptId, userId, target),
  preview: async (target: string, time: string) =>
    Service.getConfigBackupPreviewApiApiScriptsBackupPreviewGet(scriptId, userId, time, target),
  restore: async (target: string, time: string) =>
    Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
      scriptId,
      userId,
      time,
      target,
    }),
  readFile: async (target: string, time: string, path: string) =>
    Service.getConfigBackupFileApiApiScriptsBackupFileGet(scriptId, userId, time, target, path),
}

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
const ensureBAAHBackup = async (target: 'mas' | 'native') => {
  if (!userId) return
  try {
    const resp = await Service.ensureConfigBackupApiApiScriptsBackupEnsurePost({
      scriptId,
      userId,
      target,
    })
    if (resp.code !== 200) throw new Error(resp.message || t('edit.configRestoreEnsureFailed'))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.warning(t('edit.configRestoreEnsureFailed'))
  }
}

onMounted(async () => {
  if (!scriptId) {
    message.error(t('edit.missingScriptIdParameter'))
    handleCancel()
    return
  }

  // 先等脚本信息与用户就绪（新建模式内部会创建用户并写入 userId）再归档，
  // 否则新建用户首次进入会因 userId 未就绪静默跳过归档
  await loadScriptInfo()
  await nextTick()
  void ensureBAAHBackup('native')
})

onUnmounted(() => {
  // 退出编辑页：归档 MAS 编辑页字段终态（BAAH 无遮罩会话，无需停会话）
  void ensureBAAHBackup('mas')
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

.section-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
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

.activity-status {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--ant-color-text-secondary);
}

.activity-status-label {
  color: var(--ant-color-text-secondary);
}

.activity-status-name {
  color: var(--ant-color-text);
  font-weight: 600;
}

.activity-status-time {
  color: var(--ant-color-text-tertiary);
}

.activity-status-empty {
  color: var(--ant-color-text-tertiary);
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
