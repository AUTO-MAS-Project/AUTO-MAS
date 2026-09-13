<template>
  <div class="user-edit-container">
    <UserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      script-edit-segment="oknte"
      config-label="配置 OK-NTE"
      :config-loading="oknteConfigLoading"
      :config-active="showOknteConfigMask"
      :config-disabled="pageLoading || !activeUserId"
      @config="handleOkNteConfig"
      @cancel="handleCancel"
    />

    <!-- 原生 GUI 会话遮罩（配置会话 / 查看会话，公用组件对齐一条龙） -->
    <GuiSessionMask
      :open="showOknteConfigMask"
      :icon="SettingOutlined"
      :title="t('edit.okNteConfigurationProgress')"
      :description="`${t('edit.okNteGuiConfiguration')}\n${t('edit.clickSaveConfigurationWhen2')}`"
    >
      <template #actions>
        <a-button
          v-if="oknteWebsocketId"
          type="primary"
          size="large"
          @click="handleSaveOkNteConfig"
        >
          {{ t('edit.saveConfiguration') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <GuiSessionMask
      :open="showOknteViewMask"
      :icon="EyeOutlined"
      :title="t('edit.oknteViewingTitle')"
      :description="`${t('edit.oknteViewingDesc')}\n${t('edit.oknteViewingDesc2')}`"
    >
      <template #actions>
        <a-button
          v-if="oknteWebsocketId"
          type="primary"
          size="large"
          :loading="stoppingOknteConfig"
          @click="handleCloseOknteView"
        >
          {{ t('edit.oknteViewClose') }}
        </a-button>
      </template>
    </GuiSessionMask>

    <div class="user-edit-content">
      <a-card class="config-card" :loading="pageLoading">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <div class="section-header">
              <h3>{{ t('edit.basicInfo') }}</h3>
            </div>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.username') }}
                      <a-tooltip :title="t('edit.nameUsedTellUsers')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.userName"
                    :placeholder="t('edit.enterUsername')"
                    size="large"
                    @blur="saveField('Info.Name', formData.userName)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.enabled') }}
                      <a-tooltip :title="t('edit.whetherThisUserEnabled')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Info.Status"
                    size="large"
                    @change="saveField('Info.Status', formData.Info.Status)"
                  >
                    <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                    <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.account') }}
                      <a-tooltip :title="t('edit.usedSwitchAccountsLeave')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Id"
                    :placeholder="t('edit.enterAccount')"
                    size="large"
                    @blur="saveField('Info.Id', formData.Info.Id)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.password') }}
                      <a-tooltip :title="t('edit.requiredWhenSwitchingAccounts')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input-password
                    v-model:value="formData.Info.Password"
                    :placeholder="t('edit.enterPassword')"
                    size="large"
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
                      {{ t('edit.gameResource') }}
                      <a-tooltip :title="t('edit.pickGameResourceThis')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Info.Resource"
                    :placeholder="t('edit.pickResource')"
                    size="large"
                    :options="resourceOptions"
                    @change="saveField('Info.Resource', formData.Info.Resource)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.daysLeft') }}
                      <a-tooltip :title="t('edit.daysLeftAccount1')">
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

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      节点详情推送
                      <a-tooltip
                        mouse-enter-delay="0.5"
                        title="选择该用户关键节点在任务报告中的呈现方式：关闭 = 不采集；逐条 = 每条带上采集时间，一行一条；汇总 = 按成功/失败/跳过各合并为一行"
                      >
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Notify.PushLogMode"
                    size="large"
                    class="modern-select"
                    :options="pushLogModeOptions"
                    @change="saveField('Notify.PushLogMode', formData.Notify.PushLogMode)"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item>
              <template #label>
                <span class="form-label">
                  {{ t('edit.note') }}
                  <a-tooltip :title="t('edit.addNoteAboutThis')">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </span>
              </template>
              <a-textarea
                v-model:value="formData.Info.Notes"
                :placeholder="t('edit.enterNote')"
                :rows="4"
                @blur="saveField('Info.Notes', formData.Info.Notes)"
              />
            </a-form-item>
          </div>

          <div class="form-section">
            <div class="section-header">
              <h3>{{ t('edit.taskConfiguration') }}</h3>
            </div>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.startTaskTN') }}
                      <a-tooltip :title="t('edit.taskNumbersMatchOk')">
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
                      v-for="item in oknteTaskOptions"
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
                      {{ t('edit.currentLaunchArguments') }}
                      <a-tooltip :title="t('edit.argumentsGeneratedFromTask')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input :value="currentStartupArguments" size="large" readonly />
                </a-form-item>
              </a-col>
            </a-row>
          </div>
        </a-form>
      </a-card>

      <!-- OK-NTE 配置编辑器（配置恢复按钮经插槽统一放在编辑器标题行右侧） -->
      <a-card class="config-card" style="margin-top: 24px">
        <OkNteConfigEditor
          v-if="activeUserId"
          :script-id="scriptId"
          :user-id="activeUserId"
          :refresh-token="oknteConfigRefreshToken"
          @saved="handleConfigSaved"
        >
          <template #header-actions>
            <a-button size="small" @click="openRestoreModal">
              <template #icon><HistoryOutlined /></template>
              {{ t('edit.configRestoreTitle') }}
            </a-button>
          </template>
        </OkNteConfigEditor>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <UserNotifyConfig
            v-model="formData.Notify"
            :loading="pageLoading"
            :script-id="scriptId"
            :user-id="activeUserId"
            @save="saveField"
          />
        </a-form>
      </a-card>
    </div>

    <!-- ══ 配置恢复（通用组件：MAS 用户配置在前、ok-nte 原生配置在后）══ -->
    <ConfigRestoreSection
      v-model:open="restoreOpen"
      :script-name="OKNTE_DISPLAY_NAME"
      :targets="restoreTargets"
      :api="restoreApi"
      :script-desc="t('edit.oknteConfigRestoreScriptDesc')"
      :on-restored="handleRestored"
      :on-detail="handleRestoreView"
    >
      <!-- ok-nte 备份摘要为文件集结构，用插槽完全接管预览区 -->
      <template #preview="{ raw }">
        <a-empty
          v-if="!previewFiles(raw).length"
          :description="t('edit.configRestorePreviewEmpty')"
        />
        <div v-else>
          <template v-for="f in previewFiles(raw)" :key="f.name">
            <h4 class="oknte-preview-title">{{ f.label }}</h4>
            <a-descriptions :column="1" size="small" bordered class="oknte-preview-box">
              <a-descriptions-item
                v-for="row in f.summary"
                :key="row.key"
                :label="row.key"
              >
                {{ row.value }}
              </a-descriptions-item>
            </a-descriptions>
          </template>
        </div>
      </template>
    </ConfigRestoreSection>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  computed,
  h,
  nextTick,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  watch,
} from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  EyeOutlined,
  HistoryOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { Service, type OkNteUserConfig } from '@/api'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useOknteGuiSession } from '@/composables/useOknteGuiSession'
import { useSaveQueue } from '@/composables/useSaveQueue'
import UserEditHeader from '@/components/UserEditHeader.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import OkNteConfigEditor from './OkNteUserEdit/OkNteConfigEditor.vue'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('OK-NTE用户编辑')
const route = useRoute()
const router = useRouter()
const { addUser, getUsers, updateUser } = useUserApi()
const { getScript } = useScriptApi()
const {
  oknteConfigLoading,
  oknteWebsocketId,
  showOknteConfigMask,
  showOknteViewMask,
  stoppingOknteConfig,
  startSession,
  saveSession,
  stopSession,
} = useOknteGuiSession()

const scriptId = route.params.scriptId as string
let userId = (route.params.userId as string) || ''
const isEdit = ref(!!userId)
const activeUserId = ref(userId)
const scriptName = ref('OK-NTE脚本')

const pageLoading = ref(true)
const isInitializing = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { enqueue } = useSaveQueue()
const oknteConfigRefreshToken = ref(0)

/** OK-NTE 已适配任务（-t 1..19）；新版上游 DailyRoutineTask 是 -t 2 */
const OKNTE_MAX_TASK_INDEX = 19

const resourceOptions = [{ label: '官服', value: '官服' }]
// 节点详情推送模式（value 为后端 Notify.PushLogMode 取值，驱动逻辑需保持原样；label 走词表）
const pushLogModeOptions = [
  { label: t('edit.pushLogModeOff'), value: '关闭' },
  { label: t('edit.pushLogModeList'), value: '逐条' },
  { label: t('edit.pushLogModeSummary'), value: '汇总' },
]

const oknteTaskOptions = [
  { label: '1 - LauncherTask（启动游戏）', value: 1 },
  { label: '2 - DailyRoutineTask（日常任务）', value: 2 },
  { label: '3 - FishingTask（自动钓鱼）', value: 3 },
  { label: '4 - AnomalyTask（异象界域）', value: 4 },
  { label: '5 - AnomalyHunter（异象追猎）', value: 5 },
  { label: '6 - RhythmTask（自动音游）', value: 6 },
  { label: '7 - OwnerSelectionTask（店长特供）', value: 7 },
  { label: '8 - AutoHeistTask（自动粉爪大劫案）', value: 8 },
  { label: '9 - BagelAITools（呗果智能体）', value: 9 },
  { label: '10 - WhirlwindTask（自动小旋风）', value: 10 },
  { label: '11 - DSDFarmTask（九百九十九夜）', value: 11 },
  { label: '12 - CombatDetectionTestTask（自动战斗检测诊断）', value: 12 },
  { label: '13 - DiagnosisTask（诊断）', value: 13 },
  { label: '14 - DailyClaimTask（日常领取）', value: 14 },
  { label: '15 - GiftTask（羁遇赠礼）', value: 15 },
  { label: '16 - CoffeeTask（一咖舍）', value: 16 },
  { label: '17 - FountainTask（喷泉签到）', value: 17 },
  { label: '18 - FurnitureTask（异象家具）', value: 18 },
  { label: '19 - CinemaDateTask（影院约会）', value: 19 },
]

type FormSection<T> = { [K in keyof T]-?: NonNullable<T[K]> }

type OkNteNotifyForm = FormSection<NonNullable<OkNteUserConfig['Notify']>>

type OkNteUserFormData = {
  userName: string
  Info: FormSection<NonNullable<OkNteUserConfig['Info']>>
  Task: FormSection<NonNullable<OkNteUserConfig['Task']>>
  Notify: OkNteNotifyForm
  Data: FormSection<NonNullable<OkNteUserConfig['Data']>>
}

const getDefaultUserData = (): Omit<OkNteUserFormData, 'userName'> => ({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    Mode: '脚本',
    Resource: '官服',
    RemainedDay: -1,
    IfUseMasConfig: true,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
    Tag: '',
  },
  Task: {
    TaskIndex: 2,
    ExitOnFinish: true,
  },
  Notify: {
    Enabled: false,
    PushLogMode: '汇总',
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
  },
  Data: {
    LastProxyDate: '',
    ProxyTimes: 0,
    LastProxyStatus: '',
    LastTaskIndex: 0,
  },
})

const formData = reactive<OkNteUserFormData>({
  userName: '',
  ...getDefaultUserData(),
})

const currentStartupArguments = computed(() => `-t ${formData.Task.TaskIndex || 2} -e`)

const handleCancel = () => {
  void stopSession()
  router.push('/scripts')
}

const refreshOkNteConfigEditor = () => {
  oknteConfigRefreshToken.value += 1
}

const createUserImmediately = async () => {
  const resp = await addUser(scriptId)
  if (!resp?.userId) {
    throw new Error(resp?.message || '创建用户失败')
  }
  userId = resp.userId
  activeUserId.value = userId
  isEdit.value = true
  await router.replace({
    name: 'OkNteUserEdit',
    params: { scriptId, userId },
  })
}

const saveField = async (key: string, value: unknown) => {
  if (isInitializing.value || !userId) return

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

  await enqueue(async () => {
    try {
      await updateUser(scriptId, userId, patch)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    }
  }, key)
}

const saveTaskConfig = async () => {
  if (isInitializing.value || !userId) return
  formData.Task.ExitOnFinish = true
  await updateUser(scriptId, userId, {
    Task: {
      TaskIndex: formData.Task.TaskIndex,
      ExitOnFinish: true,
    },
  })
}

const handleTaskIndexChange = async (value: number) => {
  formData.Task.TaskIndex = value
  try {
    await saveTaskConfig()
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

const handleOkNteConfig = async () => {
  if (!userId) {
    message.error(t('edit.createUserBeforeConfiguring'))
    return
  }
  await startSession(userId)
}

const handleSaveOkNteConfig = () => {
  void saveSession()
}

const handleCloseOknteView = () => {
  void stopSession()
}

const loadScriptInfo = async () => {
  const detail = await getScript(scriptId)
  if (detail) {
    scriptName.value = detail.name
  }
}

const loadUser = async () => {
  pageLoading.value = true
  try {
    if (!userId) {
      await createUserImmediately()
    }
    const resp = await getUsers(scriptId, userId)
    const userIndex = resp?.index?.find(i => i.uid === userId)
    const data = resp?.data?.[userId] as OkNteUserConfig | undefined
    if (!userIndex || !data) {
      throw new Error('用户不存在或加载失败')
    }

    Object.assign(formData, {
      Info: { ...getDefaultUserData().Info, ...(data.Info || {}) },
      Task: { ...getDefaultUserData().Task, ...(data.Task || {}) },
      Notify: { ...getDefaultUserData().Notify, ...(data.Notify || {}) },
      Data: { ...getDefaultUserData().Data, ...(data.Data || {}) },
    })
    formData.Task.ExitOnFinish = true
    const taskIndex = Number(formData.Task.TaskIndex)
    if (!Number.isFinite(taskIndex) || taskIndex < 1 || taskIndex > OKNTE_MAX_TASK_INDEX) {
      formData.Task.TaskIndex = 2
    }
    await nextTick()
    formData.userName = formData.Info.Name || ''
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(t('edit.couldNotLoadUser'))
    handleCancel()
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const handleConfigSaved = () => {
  logger.info('OK-NTE 配置已保存')
}

// ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
// 专项统一名（文案参数化用）：ok-nte 统一叫「ok-nte」
const OKNTE_DISPLAY_NAME = 'ok-nte'
const restoreOpen = ref(false)

// 目标池顺序 = segmented 展示顺序：MAS 用户配置（在前）、ok-nte 原生配置（在后）
const restoreTargets: Array<{ key: string; kind: 'user' | 'script' }> = [
  { key: 'mas', kind: 'user' },
  { key: 'native', kind: 'script' },
]

// 组件调用后端：通用 /backup/* 端点（脚本/用户上下文在此闭包捕获）
const restoreApi = {
  list: async (target: string) =>
    Service.listConfigBackupsApiApiScriptsBackupListGet(scriptId, userId, target),
  preview: async (target: string, time: string) =>
    Service.getConfigBackupPreviewApiApiScriptsBackupPreviewGet(
      scriptId,
      userId,
      time,
      target
    ),
  restore: async (target: string, time: string) =>
    Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
      scriptId,
      userId,
      time,
      target,
    }),
}

const openRestoreModal = () => {
  restoreOpen.value = true
}

// 预览响应原文（unknown）收敛为文件集视图：泛用组件的 raw 插槽不带专项类型
interface OkNtePreviewFileView {
  name: string
  label: string
  summary: Array<{ key: string; value: string }>
}
const previewFiles = (raw: unknown): OkNtePreviewFileView[] =>
  (raw as { files?: OkNtePreviewFileView[] } | null)?.files ?? []

// 一键恢复成功：MAS 目录回到该时点，重拉动态表单——否则旧表单值在下次
// 保存时全量写回、静默撤销刚做的恢复（ok-nte 原生恢复不影响本页表单）
const handleRestored = (target: string) => {
  restoreOpen.value = false
  if (target === 'mas') {
    refreshOkNteConfigEditor()
  }
}

// 「查看详细配置」语义（对齐一条龙）：恢复该时点 + 拉起查看会话预览。
// 弹窗文案必须显式区分——该按钮极易被误以为只读，实际会真覆盖当前配置。
// mas 备份：恢复到 MAS 目录后启动查看会话（下发为查看的必经复制，GUI 所见
// 即备份）；原生备份：恢复到 ok-nte 本体后启动脚本级查看会话（跳过下发，
// 原生目录即备份）。查看会话结束不回写配置，原生现场由任务前快照还原。
const handleRestoreView = (target: string, item: { time: string }) => {
  Modal.confirm({
    title: t('edit.configRestoreDetailView'),
    content: h(
      'p',
      { style: { color: 'var(--ant-color-error)', margin: 0 } },
      t('edit.configRestoreDetailConfirm', { script: OKNTE_DISPLAY_NAME })
    ),
    okText: t('edit.configRestoreConfirmOk'),
    cancelText: t('edit.cancel'),
    onOk: async () => {
      try {
        const resp = await Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
          scriptId,
          userId,
          time: item.time,
          target,
        })
        // 后端失败走 HTTP 200 + body code=400，须显式检查返回体：备份不存在/
        // 配置路径未设置等抛错若被吞掉，会照常关弹窗并打开查看会话
        if (resp.code !== 200) {
          throw new Error(resp.message || t('edit.configRestoreFailed'))
        }
        restoreOpen.value = false
        if (target === 'mas') {
          await startSession(userId, true)
        } else {
          await startSession(scriptId, true)
        }
      } catch (e) {
        message.error(e instanceof Error ? e.message : t('edit.configRestoreFailed'))
      }
    },
  })
}

// 编辑会话归档（进入/退出时机，指纹去重）：与运行/会话下发前的双池归档
// （AutoProxy/ScriptConfig 的 set_oknte）配合——进入归档原生配置当前状态
// （随后可能的会话/运行都会触碰它），退出归档 MAS 配置终态（编辑会话包络）
const ensureOkNteBackup = async (target: 'mas' | 'native') => {
  if (!userId) return
  try {
    await Service.ensureConfigBackupApiApiScriptsBackupEnsurePost({
      scriptId,
      userId,
      target,
    })
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

onMounted(async () => {
  await loadScriptInfo()
  await loadUser()
  // 进入编辑页：归档 ok-nte 原生配置当前状态（MAS 触碰前的原始态）
  await ensureOkNteBackup('native')
})

// 会话结束后的表单同步（对齐一条龙）：配置会话关闭重拉动态表单（GUI 内
// 改动已回写）；查看会话关闭同样重拉（查看前刚恢复过备份）
watch(showOknteConfigMask, (now, before) => {
  if (before && !now && !showOknteViewMask.value) refreshOkNteConfigEditor()
})
watch(showOknteViewMask, (now, before) => {
  if (before && !now) refreshOkNteConfigEditor()
})

onUnmounted(() => {
  // 退出编辑页：归档 MAS 配置终态（编辑会话包络），并结束未关闭的会话
  void ensureOkNteBackup('mas')
  void stopSession()
})
</script>

<style scoped>
.user-edit-container {
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
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

/* 配置预览：逐文件的摘要标题与摘要表 */
.oknte-preview-title {
  margin: 14px 0 6px;
  font-size: 14px;
  font-weight: 600;
}

.oknte-preview-title:first-child {
  margin-top: 0;
}

.oknte-preview-box {
  margin-bottom: 4px;
}

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }
}
</style>
