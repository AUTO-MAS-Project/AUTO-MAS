<template>
  <div class="user-edit-container">
    <!-- ══ SRC 配置/查看会话遮罩（配置会话下发用户配置、查看会话只读）══ -->
    <GuiSessionMask
      :open="showSrcConfigMask"
      :icon="SettingOutlined"
      :title="t('edit.srcConfigurationProgress')"
      :description="`${t('edit.srcConfigurationThisUser')}\n${t('edit.clickSaveConfigurationWhen2')}`"
    >
      <template #actions>
        <a-button
          v-if="srcTaskId"
          type="primary"
          size="large"
          :loading="stoppingSrcConfig"
          @click="handleSaveSRCConfig"
        >
          {{ t('edit.saveConfiguration') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <GuiSessionMask
      :open="showSrcViewMask"
      :icon="EyeOutlined"
      :title="t('edit.srcViewingTitle')"
      :description="`${t('edit.srcViewingDesc')}\n${t('edit.srcViewingDesc2')}`"
    >
      <template #actions>
        <a-button
          type="primary"
          size="large"
          :loading="stoppingSrcConfig"
          @click="handleSaveSRCConfig"
        >
          {{ t('edit.srcViewClose') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <!-- 头部组件 -->
    <SRCUserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      :user-mode="formData.Info.Mode"
      :src-config-loading="srcConfigLoading"
      :show-src-config-mask="showSrcConfigMask"
      :loading="loading"
      @handle-s-r-c-config="startConfigSession(false)"
      @handle-cancel="handleCancel"
    />

    <div class="user-edit-content">
      <a-card class="config-card">
        <a-form
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <!-- 基本信息组件 -->
          <BasicInfoSection
            v-model:form-data="formData"
            :loading="loading"
            :server-options="serverOptions"
            @save="handleFieldSave"
            @mode-change="handleConfigModeChange"
            @quick-config-change="handleQuickConfigChange"
          />

          <!-- 关卡配置组件（恢复按钮挂标题行右侧） -->
          <StageConfigSection
            v-model:form-data="formData"
            :loading="loading"
            @save="handleFieldSave"
          >
            <template #header-actions>
              <div class="section-header-actions">
                <a-button size="small" @click="restoreOpen = true">
                  <template #icon>
                    <HistoryOutlined />
                  </template>
                  {{ t('edit.configRestoreTitle') }}
                </a-button>
              </div>
            </template>
          </StageConfigSection>

          <!-- 额外脚本组件 -->
          <ExtraScriptSection
            v-model:form-data="formData"
            :loading="loading"
            @save="handleFieldSave"
          />

          <!-- 通知配置组件 -->
          <UserNotifyConfig
            v-model="formData.Notify"
            :loading="loading"
            :script-id="scriptId"
            :user-id="userId"
            @save="handleFieldSave"
          />
        </a-form>
      </a-card>
    </div>

    <!-- ══ 配置恢复（通用组件：MAS 用户配置在前、SRC 原生配置在后）══ -->
    <ConfigRestoreSection
      v-model:open="restoreOpen"
      :script-name="SRC_DISPLAY_NAME"
      :targets="restoreTargets"
      :api="restoreApi"
      :user-desc="t('edit.srcConfigRestoreUserDesc')"
      :script-desc="t('edit.srcConfigRestoreScriptDesc')"
      :on-restored="handleRestored"
      :on-detail="handleRestoreView"
    >
      <!-- mas 备份为字段侧车分区、native 备份为关键字段反读分区 -->
      <template #preview="{ raw }">
        <a-empty
          v-if="!previewSections(raw).length"
          :description="t('edit.configRestorePreviewEmpty')"
        />
        <div v-else>
          <template v-for="s in previewSections(raw)" :key="s.name">
            <h4 class="src-preview-title">{{ s.label }}</h4>
            <a-descriptions
              v-if="s.rows && s.rows.length"
              :column="1"
              size="small"
              bordered
              class="src-preview-box"
            >
              <a-descriptions-item v-for="row in s.rows" :key="row.key" :label="row.key">
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
import { computed, h, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { EyeOutlined, HistoryOutlined, SettingOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { useSaveQueue } from '@/composables/useSaveQueue'
import { useWebSocket } from '@/composables/useWebSocket.ts'
import {
  WS_TASK_COMPLETED,
  WS_TASK_NOTICE,
  type WSTaskCompletedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn.ts'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'

const logger = window.electronAPI.getLogger('SRC用户编辑')

// 导入拆分的组件
import SRCUserEditHeader from '@/views/SRCUserEdit/SRCUserEditHeader.vue'
import BasicInfoSection from '@/views/SRCUserEdit/BasicInfoSection.vue'
import StageConfigSection from '@/views/SRCUserEdit/StageConfigSection.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'

const { t } = useI18n()

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()
const { subscribe, unsubscribe } = useWebSocket()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)
const isInitializing = ref(true) // 标记是否正在初始化
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { enqueue } = useSaveQueue()

// SRC 会话相关状态
const srcConfigLoading = ref(false)
const stoppingSrcConfig = ref(false)
const showSrcConfigMask = ref(false)
const showSrcViewMask = ref(false)
// 当前会话类型（查看会话静默关闭、完成提示与配置会话不同）
const currentSessionViewOnly = ref(false)
const srcSubscriptionIds = ref<string[]>([])
const srcTaskId = ref<string | null>(null)
let srcConfigTimeout: number | null = null

// 路由参数
const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId) // 使用 ref 以便在创建后更新

// 脚本信息
const scriptName = ref('')

// 服务器选项
const serverOptions = [
  { label: '官服', value: 'CN-Official' },
  { label: 'B服', value: 'CN-Bilibili' },
  { label: '越南服', value: 'VN-Official' },
  { label: '美服', value: 'OVERSEA-America' },
  { label: '亚服', value: 'OVERSEA-Asia' },
  { label: '欧服', value: 'OVERSEA-Europe' },
  { label: '港澳台服', value: 'OVERSEA-TWHKMO' },
]

// SRC脚本默认用户数据
const getDefaultSRCUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    Mode: '脚本',
    IfQuickConfig: true,
    Server: 'CN-Official',
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
    Tag: '',
  },
  Stage: {
    Channel: 'Relic',
    Relic: '-',
    Materials: '-',
    Ornament: '-',
    ExtractReservedTrailblazePower: false,
    UseFuel: false,
    FuelReserve: 5,
    EchoOfWar: '-',
    SimulatedUniverseWorld: '-',
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

// 创建扁平化的表单数据
const formData = reactive({
  userName: '',
  ...getDefaultSRCUserData(),
})

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
const syncUserName = () => {
  if (formData.Info.Name !== formData.userName) {
    formData.Info.Name = formData.userName
  }
}

// 即时保存单个字段变更
const handleFieldSave = async (key: string, value: any) => {
  // 如果正在初始化，或者是新用户（还没有userId），不执行保存
  if (isInitializing.value || !userId) {
    logger.debug(`跳过保存: 初始化=${isInitializing.value}, userId=${userId}`)
    return
  }

  // 如果是userName字段，需要同步到Info.Name
  if (key === 'userName') {
    syncUserName()
    key = 'Info.Name'
    value = formData.Info.Name
  }

  await enqueue(async () => {
    try {
      const parts = key.split('.')
      let userData: Record<string, any> = {}
      let current = userData

      // 构建嵌套结构
      for (let i = 0; i < parts.length - 1; i++) {
        current[parts[i]] = {}
        current = current[parts[i]]
      }
      current[parts[parts.length - 1]] = value

      logger.debug(`保存字段: ${key} = ${JSON.stringify(value)}`)
      const success = await updateUser(scriptId, userId, userData)
      if (success) {
        logger.info(`字段已保存: ${key}`)
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存字段失败: ${errorMsg}`)
    }
  }, key)
}

// 快速配置开关：与配置来源独立，真实保存
const handleQuickConfigChange = async (value: boolean) => {
  formData.Info.IfQuickConfig = value
  await handleFieldSave('Info.IfQuickConfig', value)
}

// 配置来源切换：校验 value ∈ options → 赋值 Info.Mode → 保存
const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['脚本', '用户', '直控'].includes(value)) return
  formData.Info.Mode = value as '脚本' | '用户' | '直控'
  await handleFieldSave('Info.Mode', formData.Info.Mode)
}

// ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
// 专项统一名（文案参数化用）：SRC 统一叫「src」
const SRC_DISPLAY_NAME = 'src'
const restoreOpen = ref(false)

// 目标池顺序 = segmented 展示顺序：MAS 用户配置（在前）、SRC 原生配置（在后）
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

interface SrcPreviewRow {
  key: string
  value: string
}
interface SrcPreviewSection {
  name: string
  label: string
  rows?: SrcPreviewRow[]
}
const previewSections = (raw: unknown): SrcPreviewSection[] =>
  (raw as { sections?: SrcPreviewSection[] } | null)?.sections ?? []

// 一键恢复成功：mas 恢复回填页面核心字段（Stage 等），需重拉表单；
// native 恢复写 SRC 本体 config/，MAS 表单不受影响
const handleRestored = async (target: string) => {
  restoreOpen.value = false
  if (target === 'mas') {
    isInitializing.value = true
    await loadUserData()
    isInitializing.value = false
  }
}

// 「查看详细配置」语义（对齐一条龙）：恢复该时点 + 拉起查看会话预览。
// mas 备份：恢复到 MAS 目录后启动用户级查看会话（下发为查看的必经复制，
// GUI 所见即备份）；原生备份：恢复到 SRC 本体后启动脚本级查看会话（跳过
// 下发，原生目录即备份）。查看会话结束不回写配置，原生现场由任务前快照还原。
const handleRestoreView = (target: string, item: { time: string }) => {
  Modal.confirm({
    title: t('edit.configRestoreDetailView'),
    content: h(
      'p',
      { style: { color: 'var(--ant-color-error)', margin: 0 } },
      t('edit.configRestoreDetailConfirm', { script: SRC_DISPLAY_NAME })
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
        // 路径未设置等抛错若被吞掉，会照常关弹窗并打开查看会话
        if (resp.code !== 200) {
          throw new Error(resp.message || t('edit.configRestoreFailed'))
        }
        restoreOpen.value = false
        if (target === 'mas') {
          await startConfigSession(true)
        } else {
          await startScriptLevelViewSession()
        }
      } catch (e) {
        message.error(e instanceof Error ? e.message : t('edit.configRestoreFailed'))
      }
    },
  })
}

// 脚本级查看会话：以脚本 ID 为会话任务标识启动（调度层把脚本级设置任务
// 归属解析为 Default，跳过用户配置下发——原生目录即所选备份）
const startScriptLevelViewSession = async () => {
  const previousUserId = userId
  userId = scriptId
  try {
    await startConfigSession(true)
  } finally {
    userId = previousUserId
  }
}

// 编辑会话归档（进入/退出时机，指纹去重）：与运行/会话下发前的双池归档
// （AutoProxy/ScriptConfig 的 set_src）配合——进入归档原生配置当前状态
// （MAS 触碰前原始态），退出归档 MAS 配置终态（编辑会话包络）
const ensureSrcBackup = async (target: 'mas' | 'native') => {
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

// 初始化
onMounted(async () => {
  await loadScriptInfo()
  if (isEdit.value) {
    await loadUserData()
  }
  // 设置初始化完成，允许后续编辑触发保存
  await nextTick()
  isInitializing.value = false
  // 编辑界面进入：归档 SRC 原生配置当前状态（须在 userId 就绪后）
  void ensureSrcBackup('native')
})

const loadScriptInfo = async () => {
  try {
    const scriptDetail = await getScript(scriptId)
    if (scriptDetail) {
      scriptName.value = scriptDetail.name
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
  }
}

const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)

    if (userResponse && userResponse.code === 200) {
      // 查找指定的用户数据
      const userIndex = userResponse.index.find((index: any) => index.uid === userId)
      if (userIndex && userResponse.data[userId]) {
        const userData = userResponse.data[userId] as any

        // 填充SRC用户数据
        if (userIndex.type === 'SrcUserConfig') {
          Object.assign(formData, {
            Info: { ...getDefaultSRCUserData().Info, ...userData.Info },
            Stage: { ...getDefaultSRCUserData().Stage, ...userData.Stage },
            Notify: { ...getDefaultSRCUserData().Notify, ...userData.Notify },
            Data: { ...getDefaultSRCUserData().Data, ...userData.Data },
          })

          // 同步扁平字段
          await nextTick()
          formData.userName = formData.Info.Name || ''
        } else {
          message.error(t('edit.userTypeDoesNot'))
          router.push('/scripts')
        }
      } else {
        message.error(t('edit.userDoesNotExist'))
        router.push('/scripts')
      }
    } else {
      message.error(t('edit.couldNotLoadUser'))
      router.push('/scripts')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载用户失败: ${errorMsg}`)
    message.error(t('edit.couldNotLoadUser'))
    router.push('/scripts')
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

// ══ 会话 UI 清理（订阅 / 任务号 / 遮罩 / 超时定时器）══
const closeSessionUi = () => {
  for (const subscriptionId of srcSubscriptionIds.value) {
    unsubscribe(subscriptionId)
  }
  srcSubscriptionIds.value = []
  srcTaskId.value = null
  showSrcConfigMask.value = false
  showSrcViewMask.value = false
  if (srcConfigTimeout) {
    window.clearTimeout(srcConfigTimeout)
    srcConfigTimeout = null
  }
}

// 处理SRC配置/查看会话（viewOnly=true 为只读查看会话：界面显示所选备份
// 内容，结束不回写；配置会话保存回用户配置目录）
const startConfigSession = async (viewOnly: boolean) => {
  try {
    srcConfigLoading.value = true
    currentSessionViewOnly.value = viewOnly

    // 如果已有连接，先断开
    if (srcSubscriptionIds.value.length > 0) {
      closeSessionUi()
    }

    // 调用后端启动任务接口，传入 userId 作为 taskId 与设置模式
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: userId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
      viewOnly,
    })

    if (response && response.taskId) {
      const wsId = response.taskId

      // 订阅 websocket
      const subscriptionIds = [
        // 处理任务提示中的错误消息（不取消订阅，等待任务结束消息）
        subscribe({ id: wsId, type: WS_TASK_NOTICE }, wsMessage => {
          const data = wsMessage.data as unknown as WSTaskNoticeData
          if (data.level === 'error') {
            logger.error(
              `用户 ${formData.Info?.Name || formData.userName} SRC会话异常:${data.message}`
            )
            message.error(t('edit.srcConfigurationFailedP0', { p0: data.message }))
          }
        }),
        // 处理任务结束消息
        subscribe({ id: wsId, type: WS_TASK_COMPLETED }, wsMessage => {
          const data = wsMessage.data as unknown as WSTaskCompletedData
          logger.info(`用户 ${formData.Info?.Name || formData.userName} SRC会话任务已结束`)
          if (data.outcome === 'success' && !viewOnly) {
            message.success(
              t('edit.configurationUserP0Done', { p0: formData.Info?.Name || formData.userName })
            )
          }
          closeSessionUi()
        }),
      ]

      srcSubscriptionIds.value = subscriptionIds
      srcTaskId.value = wsId
      if (viewOnly) {
        showSrcViewMask.value = true
        message.success(t('edit.srcViewOpened'))
      } else {
        showSrcConfigMask.value = true
        message.success(
          t('edit.startedSrcSetupUser', { p0: formData.Info?.Name || formData.userName })
        )
      }

      // 设置 30 分钟超时：自动结束会话（对齐 MAA——配置会话超时自动保存、
      // 查看会话静默关闭；只关遮罩不停任务会让 webui 残留、恢复被守卫拦截）
      srcConfigTimeout = window.setTimeout(
        () => {
          const taskId = srcTaskId.value
          if (taskId) {
            void (async () => {
              try {
                await Service.stopTaskApiDispatchStopPost({ taskId })
              } catch (e) {
                logger.error(e instanceof Error ? e.message : String(e))
              }
              closeSessionUi()
              if (!viewOnly) {
                message.info(
                  t('edit.configurationSessionUserP0', {
                    p0: formData.Info?.Name || formData.userName,
                  })
                )
              }
            })()
          }
          srcConfigTimeout = null
        },
        30 * 60 * 1000
      )
    } else {
      message.error(
        response?.message || (viewOnly ? t('edit.srcViewStartFailed') : t('edit.couldNotStartSrc'))
      )
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动SRC会话失败: ${errorMsg}`)
    message.error(viewOnly ? t('edit.srcViewStartFailed') : t('edit.couldNotStartSrc'))
  } finally {
    srcConfigLoading.value = false
  }
}

// 保存SRC配置（配置会话）/ 关闭查看（查看会话）——都是停止后台任务
const handleSaveSRCConfig = async () => {
  const viewOnly = currentSessionViewOnly.value
  try {
    const taskId = srcTaskId.value
    if (!taskId) {
      message.error(t('edit.noActiveConfigurationSession'))
      return
    }

    stoppingSrcConfig.value = true
    const response = await Service.stopTaskApiDispatchStopPost({ taskId })
    if (response && response.code === 200) {
      closeSessionUi()
      if (!viewOnly) {
        message.success(
          t('edit.configurationUserP0Was', { p0: formData.Info?.Name || formData.userName })
        )
      }
    } else {
      message.error(response?.message || t('edit.couldNotSaveSrc'))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`结束SRC会话失败: ${errorMsg}`)
    message.error(t('edit.couldNotSaveSrc'))
  } finally {
    stoppingSrcConfig.value = false
  }
}

// 如果是新建模式，在组件挂载后自动创建用户并获取userId
if (!userId) {
  onMounted(async () => {
    // 等待脚本信息加载完成
    await loadScriptInfo()
    // 创建新用户
    const result = await addUser(scriptId)
    if (result && result.userId) {
      userId = result.userId
      isEdit.value = true
      logger.info(`新建用户，获取userId: ${userId}`)
    } else {
      message.error(t('edit.couldNotCreateUser'))
      router.push('/scripts')
    }
    // 标记初始化完成
    isInitializing.value = false
    // 编辑界面进入：归档 SRC 原生配置当前状态（须在 userId 就绪后）
    void ensureSrcBackup('native')
  })
}

onUnmounted(() => {
  // 退出编辑页：先停会话再归档 MAS 侧终态——并行会与 final_task 的回写
  // 撞车，归档到半程状态；会话未开时跳过停止，不影响归档时机
  void (async () => {
    const taskId = srcTaskId.value
    if (taskId) {
      try {
        await Service.stopTaskApiDispatchStopPost({ taskId })
      } catch (e) {
        logger.error(e instanceof Error ? e.message : String(e))
      }
      closeSessionUi()
    }
    await ensureSrcBackup('mas')
  })()
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

.config-form {
  max-width: none;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .user-edit-content {
    max-width: 100%;
  }
}

/* 配置恢复按钮（挂关卡配置标题行，对齐 BAAH/General 套件） */
.section-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 配置恢复预览（分区行；弹窗内滚动由通用组件负责） */
.src-preview-title {
  font-size: 15px;
  font-weight: 600;
  margin: 12px 0 8px;
  color: var(--ant-color-text);
}

.src-preview-box {
  margin-bottom: 8px;
}
</style>
