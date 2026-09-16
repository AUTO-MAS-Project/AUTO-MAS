<template>
  <div class="user-edit-container">
    <!-- SRC配置遮罩层 -->
    <teleport to="body">
      <div v-if="showSrcConfigMask" class="src-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: '#1890ff' }" />
          </div>
          <h2 class="mask-title">{{ t('edit.srcConfigurationProgress') }}</h2>
          <p class="mask-description">
            {{ t('edit.srcConfigurationThisUser') }}
            <br />
            配置完成后，请点击"保存配置"按钮来结束配置会话。
          </p>
          <div class="mask-actions">
            <a-button v-if="srcTaskId" type="primary" size="large" @click="handleSaveSRCConfig">
              {{ t('edit.saveConfiguration') }}
            </a-button>
          </div>
        </div>
      </div>
    </teleport>
    <!-- 头部组件 -->
    <SRCUserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      :user-mode="formData.Info.Mode"
      :src-config-loading="srcConfigLoading"
      :show-src-config-mask="showSrcConfigMask"
      :loading="loading"
      :config-locked="configLocked"
      @handle-s-r-c-config="handleSRCConfig"
      @handle-cancel="handleCancel"
    />

    <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
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
          />

          <!-- 关卡配置组件 -->
          <a-flex
            class="section-header"
            justify="space-between"
            align="center"
            wrap="wrap"
            gap="small"
          >
            <h3>{{ t('edit.stageConfiguration') }}</h3>
            <a-space>
              <span>{{ t('edit.enableQuickConfiguration') }}</span>
              <a-switch
                :checked="formData.Info.IfQuickConfig"
                :disabled="loading || isInitializing || isSaving"
                :aria-label="t('edit.enableQuickConfiguration')"
                @change="handleQuickConfigChange"
              />
            </a-space>
          </a-flex>
          <StageConfigSection
            v-if="formData.Info.IfQuickConfig"
            v-model:form-data="formData"
            :loading="loading"
            @save="handleFieldSave"
          />

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
    </ConfigLockPanel>
  </div>
</template>

<script setup lang="ts">
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { useI18n } from 'vue-i18n'
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { SettingOutlined } from '@ant-design/icons-vue'
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
const { enqueue, isSaving } = useSaveQueue()

// SRC配置相关状态
const srcConfigLoading = ref(false)
const showSrcConfigMask = ref(false)
const srcSubscriptionIds = ref<string[]>([])
const srcTaskId = ref<string | null>(null)
let srcConfigTimeout: number | null = null

// 路由参数
const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId) // 使用 ref 以便在创建后更新
const { configLocked } = useScriptConfigLock(() => scriptId)

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

  return await enqueue(async () => {
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
      return success
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存字段失败: ${errorMsg}`)
    }
  }, key)
}

// 快速配置开关：与配置来源独立，真实保存
const handleQuickConfigChange = async (value: boolean) => {
  const previous = formData.Info.IfQuickConfig
  formData.Info.IfQuickConfig = value
  if (!(await handleFieldSave('Info.IfQuickConfig', value))) {
    formData.Info.IfQuickConfig = previous
  }
}

// 配置来源切换：校验 value ∈ options → 赋值 Info.Mode → 保存
const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['脚本', '用户', '直控'].includes(value)) return
  formData.Info.Mode = value as '脚本' | '用户' | '直控'
  await handleFieldSave('Info.Mode', formData.Info.Mode)
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

// 处理SRC配置
const handleSRCConfig = async () => {
  if (configLocked.value) return
  try {
    srcConfigLoading.value = true

    // 如果已有连接，先断开
    if (srcSubscriptionIds.value.length > 0) {
      for (const subscriptionId of srcSubscriptionIds.value) {
        unsubscribe(subscriptionId)
      }
      srcSubscriptionIds.value = []
      srcTaskId.value = null
      showSrcConfigMask.value = false
      if (srcConfigTimeout) {
        window.clearTimeout(srcConfigTimeout)
        srcConfigTimeout = null
      }
    }

    // 调用后端启动任务接口，传入 userId 作为 taskId 与设置模式
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: userId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
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
              `用户 ${formData.Info?.Name || formData.userName} SRC配置异常:${data.message}`
            )
            message.error(t('edit.srcConfigurationFailedP0', { p0: data.message }))
          }
        }),
        // 处理任务结束消息
        subscribe({ id: wsId, type: WS_TASK_COMPLETED }, wsMessage => {
          const data = wsMessage.data as unknown as WSTaskCompletedData
          logger.info(`用户 ${formData.Info?.Name || formData.userName} SRC配置任务已结束`)
          // 根据结果显示不同消息
          if (data.outcome === 'success') {
            message.success(
              t('edit.configurationUserP0Done', { p0: formData.Info?.Name || formData.userName })
            )
          }
          // 清理连接
          for (const subscriptionId of srcSubscriptionIds.value) {
            unsubscribe(subscriptionId)
          }
          srcSubscriptionIds.value = []
          srcTaskId.value = null
          showSrcConfigMask.value = false
          if (srcConfigTimeout) {
            window.clearTimeout(srcConfigTimeout)
            srcConfigTimeout = null
          }
        }),
      ]

      srcSubscriptionIds.value = subscriptionIds
      srcTaskId.value = wsId
      showSrcConfigMask.value = true
      message.success(
        t('edit.startedSrcSetupUser', { p0: formData.Info?.Name || formData.userName })
      )

      // 设置 30 分钟超时自动断开
      srcConfigTimeout = window.setTimeout(
        () => {
          if (srcSubscriptionIds.value.length > 0) {
            for (const subscriptionId of srcSubscriptionIds.value) {
              unsubscribe(subscriptionId)
            }
            srcSubscriptionIds.value = []
            srcTaskId.value = null
            showSrcConfigMask.value = false
            message.info(
              t('edit.configurationSessionUserP0', { p0: formData.Info?.Name || formData.userName })
            )
          }
          srcConfigTimeout = null
        },
        30 * 60 * 1000
      )
    } else {
      message.error(response?.message || '启动SRC配置失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动SRC配置失败: ${errorMsg}`)
    message.error(t('edit.couldNotStartSrc'))
  } finally {
    srcConfigLoading.value = false
  }
}

// 保存SRC配置
const handleSaveSRCConfig = async () => {
  try {
    const taskId = srcTaskId.value
    if (!taskId) {
      message.error(t('edit.noActiveConfigurationSession'))
      return
    }

    const response = await Service.stopTaskApiDispatchStopPost({ taskId })
    if (response && response.code === 200) {
      for (const subscriptionId of srcSubscriptionIds.value) {
        unsubscribe(subscriptionId)
      }
      srcSubscriptionIds.value = []
      srcTaskId.value = null
      showSrcConfigMask.value = false
      if (srcConfigTimeout) {
        window.clearTimeout(srcConfigTimeout)
        srcConfigTimeout = null
      }
      message.success(
        t('edit.configurationUserP0Was', { p0: formData.Info?.Name || formData.userName })
      )
    } else {
      message.error(response?.message || '保存配置失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存SRC配置失败: ${errorMsg}`)
    message.error(t('edit.couldNotSaveSrc'))
  }
}

// 如果是新建模式，在组件挂载后自动创建用户并获取userId
if (!userId) {
  onMounted(async () => {
    // 等待脚本信息加载完成
    await loadScriptInfo()
    if (configLocked.value) {
      isInitializing.value = false
      return
    }

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
  })
}
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

/* SRC 配置遮罩样式（与 MAA 一致） */
.src-config-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.mask-content {
  background: var(--ant-color-bg-elevated);
  border-radius: 8px;
  padding: 24px;
  max-width: 480px;
  width: 100%;
  text-align: center;
  box-shadow:
    0 6px 16px 0 rgba(0, 0, 0, 0.08),
    0 3px 6px -4px rgba(0, 0, 0, 0.12),
    0 9px 28px 8px rgba(0, 0, 0, 0.05);
  border: 1px solid var(--ant-color-border);
}

.mask-icon {
  margin-bottom: 16px;
}

.mask-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--ant-color-text);
}

.mask-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 24px;
  line-height: 1.5;
}

.mask-actions {
  display: flex;
  justify-content: center;
}
</style>
