<template>
  <div class="user-edit-container">
    <!-- SRC配置遮罩层 -->
    <teleport to="body">
      <div v-if="showSrcConfigMask" class="src-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: '#1890ff' }" />
          </div>
          <h2 class="mask-title">正在进行SRC配置</h2>
          <p class="mask-description">
            当前正在配置该用户的 SRC，请在 SRC 配置界面完成相关设置。
            <br />
            配置完成后，请点击"保存配置"按钮来结束配置会话。
          </p>
          <div class="mask-actions">
            <a-button
              v-if="srcWebsocketId"
              type="primary"
              size="large"
              @click="handleSaveSRCConfig"
            >
              保存配置
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
      @handle-s-r-c-config="handleSRCConfig"
      @handle-cancel="handleCancel"
    />

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
      <a-spin :spinning="loading" class="config-shell">
        <a-form
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <!-- 基本信息组件 -->
          <BasicInfoSection
            ref="basicInfoRef"
            :form-data="formData"
            :loading="loading"
            :server-options="serverOptions"
            :has-stored-password="hasStoredPassword"
            @save="handleFieldSave"
            @sensitive-save="handleSensitiveSave"
          />

          <!-- 关卡配置组件 -->
          <StageConfigSection :form-data="formData" :loading="loading" @save="handleFieldSave" />

          <!-- 额外脚本组件 -->
          <ExtraScriptSection :form-data="formData" :loading="loading" @save="handleFieldSave" />

          <!-- 通知配置组件 -->
          <NotifyConfigSection
            ref="notifyRef"
            :form-data="formData"
            :loading="loading"
            :script-id="scriptId"
            :user-id="userId"
            :has-stored-server-chan-key="hasStoredServerChanKey"
            @save="handleFieldSave"
            @sensitive-save="handleSensitiveSave"
          />
        </a-form>
      </a-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { SettingOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { useWebSocket } from '@/composables/useWebSocket.ts'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn.ts'

const logger = window.electronAPI.getLogger('SRC用户编辑')

// 导入拆分的组件
import SRCUserEditHeader from '@/views/SRCUserEdit/SRCUserEditHeader.vue'
import BasicInfoSection from '@/views/SRCUserEdit/BasicInfoSection.vue'
import StageConfigSection from '@/views/SRCUserEdit/StageConfigSection.vue'
import NotifyConfigSection from '@/views/SRCUserEdit/NotifyConfigSection.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()
const { subscribe, unsubscribe } = useWebSocket()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)
const isInitializing = ref(true) // 标记是否正在初始化
const isSaving = ref(false) // 标记是否正在保存
const saveError = ref('')
const hasStoredPassword = ref(false)
const hasStoredServerChanKey = ref(false)
const basicInfoRef = ref<InstanceType<typeof BasicInfoSection>>()
const notifyRef = ref<InstanceType<typeof NotifyConfigSection>>()

// SRC配置相关状态
const srcConfigLoading = ref(false)
const showSrcConfigMask = ref(false)
const srcSubscriptionId = ref<string | null>(null)
const srcWebsocketId = ref<string | null>(null)
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
    Mode: '简洁',
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
    IfPassCheck: true,
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
      { required: true, message: '请输入用户名', trigger: 'blur' },
      { min: 1, max: 50, message: '用户名长度应在1-50个字符之间', trigger: 'blur' },
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
  // 如果正在初始化或正在保存，或者是新用户（还没有userId），不执行保存
  if (isInitializing.value || isSaving.value || !userId) {
    logger.debug(
      `跳过保存: 初始化=${isInitializing.value}, 保存中=${isSaving.value}, userId=${userId}`
    )
    return
  }

  // 如果是userName字段，需要同步到Info.Name
  if (key === 'userName') {
    syncUserName()
    key = 'Info.Name'
    value = formData.Info.Name
  }

  isSaving.value = true
  saveError.value = ''
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
    } else {
      saveError.value = `保存失败：${key}`
      logger.error(`字段保存失败: ${key}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存字段失败: ${errorMsg}`)
    saveError.value = `保存失败：${errorMsg}`
  } finally {
    isSaving.value = false
  }
}

type SrcSensitiveKey = 'Info.Password' | 'Notify.ServerChanKey'

const handleSensitiveSave = async (
  key: SrcSensitiveKey,
  intent: 'replace' | 'clear',
  value = ''
) => {
  if (isInitializing.value || isSaving.value || !userId) return
  isSaving.value = true
  saveError.value = ''
  try {
    const patch =
      key === 'Info.Password'
        ? { Info: { Password: intent === 'clear' ? '' : value } }
        : { Notify: { ServerChanKey: intent === 'clear' ? '' : value } }
    const success = await updateUser(scriptId, userId, patch)
    if (!success) throw new Error('用户配置更新未成功')

    if (key === 'Info.Password') {
      hasStoredPassword.value = intent !== 'clear'
      basicInfoRef.value?.resetPasswordDraft()
    } else {
      hasStoredServerChanKey.value = intent !== 'clear'
      notifyRef.value?.resetServerChanKeyDraft()
    }
    logger.info(`敏感字段已${intent === 'clear' ? '清空' : '保存'}: ${key}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    const label = key === 'Info.Password' ? '密码' : 'Server酱密钥'
    saveError.value = `${label}${intent === 'clear' ? '清空' : '保存'}失败：${errorMsg}`
    logger.error(`敏感字段保存失败: ${key}: ${errorMsg}`)
    if (intent === 'clear') throw error
  } finally {
    isSaving.value = false
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
          hasStoredPassword.value = Boolean(userData.Info?.Password)
          hasStoredServerChanKey.value = Boolean(userData.Notify?.ServerChanKey)
          Object.assign(formData, {
            Info: { ...getDefaultSRCUserData().Info, ...userData.Info, Password: '' },
            Stage: { ...getDefaultSRCUserData().Stage, ...userData.Stage },
            Notify: {
              ...getDefaultSRCUserData().Notify,
              ...userData.Notify,
              ServerChanKey: '',
            },
            Data: { ...getDefaultSRCUserData().Data, ...userData.Data },
          })
          basicInfoRef.value?.resetPasswordDraft()
          notifyRef.value?.resetServerChanKeyDraft()

          // 同步扁平字段
          await nextTick()
          formData.userName = formData.Info.Name || ''
        } else {
          message.error('用户类型不匹配')
          router.push('/scripts')
        }
      } else {
        message.error('用户不存在')
        router.push('/scripts')
      }
    } else {
      message.error('加载用户失败')
      router.push('/scripts')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载用户失败: ${errorMsg}`)
    message.error('加载用户失败')
    router.push('/scripts')
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

// 处理SRC配置
const handleSRCConfig = async () => {
  try {
    srcConfigLoading.value = true

    // 如果已有连接，先断开
    if (srcSubscriptionId.value) {
      unsubscribe(srcSubscriptionId.value)
      srcSubscriptionId.value = null
      srcWebsocketId.value = null
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
      const subscriptionId = subscribe({ id: wsId }, (wsMessage: any) => {
        if (wsMessage.type === 'error') {
          logger.error(
            `用户 ${formData.Info?.Name || formData.userName} SRC配置错误:${wsMessage.data}`
          )
          message.error(`SRC配置连接失败: ${wsMessage.data}`)
          unsubscribe(subscriptionId)
          srcSubscriptionId.value = null
          srcWebsocketId.value = null
          showSrcConfigMask.value = false
          if (srcConfigTimeout) {
            window.clearTimeout(srcConfigTimeout)
            srcConfigTimeout = null
          }
          return
        }

        // 处理Info类型的错误消息（显示错误但不取消订阅，等待Signal消息）
        if (wsMessage.type === 'Info' && wsMessage.data && wsMessage.data.Error) {
          logger.error(
            `用户 ${formData.Info?.Name || formData.userName} SRC配置异常:${wsMessage.data.Error}`
          )
          message.error(`SRC配置失败: ${wsMessage.data.Error}`)
          // 不取消订阅，等待Signal类型的Accomplish消息
          return
        }

        // 处理任务结束消息（Signal类型且包含Accomplish字段）
        if (
          wsMessage.type === 'Signal' &&
          wsMessage.data &&
          wsMessage.data.Accomplish !== undefined
        ) {
          logger.info(`用户 ${formData.Info?.Name || formData.userName} SRC配置任务已结束`)
          // 根据结果显示不同消息
          const result = wsMessage.data.Accomplish
          if (result && !result.includes('异常') && !result.includes('错误')) {
            message.success(`用户 ${formData.Info?.Name || formData.userName} 的配置已完成`)
          }
          // 清理连接
          unsubscribe(subscriptionId)
          srcSubscriptionId.value = null
          srcWebsocketId.value = null
          showSrcConfigMask.value = false
          if (srcConfigTimeout) {
            window.clearTimeout(srcConfigTimeout)
            srcConfigTimeout = null
          }
        }
      })

      srcSubscriptionId.value = subscriptionId
      srcWebsocketId.value = wsId
      showSrcConfigMask.value = true
      message.success(`已开始配置用户 ${formData.Info?.Name || formData.userName} 的SRC设置`)

      // 设置 30 分钟超时自动断开
      srcConfigTimeout = window.setTimeout(
        () => {
          if (srcSubscriptionId.value) {
            unsubscribe(srcSubscriptionId.value)
            srcSubscriptionId.value = null
            srcWebsocketId.value = null
            showSrcConfigMask.value = false
            message.info(`用户 ${formData.Info?.Name || formData.userName} 的配置会话已超时断开`)
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
    message.error('启动SRC配置失败')
  } finally {
    srcConfigLoading.value = false
  }
}

// 保存SRC配置
const handleSaveSRCConfig = async () => {
  try {
    const websocketId = srcWebsocketId.value
    if (!websocketId) {
      message.error('未找到活动的配置会话')
      return
    }

    const response = await Service.stopTaskApiDispatchStopPost({ taskId: websocketId })
    if (response && response.code === 200) {
      if (srcSubscriptionId.value) {
        unsubscribe(srcSubscriptionId.value)
        srcSubscriptionId.value = null
      }
      srcWebsocketId.value = null
      showSrcConfigMask.value = false
      if (srcConfigTimeout) {
        window.clearTimeout(srcConfigTimeout)
        srcConfigTimeout = null
      }
      message.success(`用户 ${formData.Info?.Name || formData.userName} 的配置已保存`)
    } else {
      message.error(response?.message || '保存配置失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存SRC配置失败: ${errorMsg}`)
    message.error('保存SRC配置失败')
  }
}

// 保存用户（用于新建时初始创建）
// 在新建模式下，需要先创建用户获取userId，再更新数据
const _saveNewUser = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
    syncUserName()

    const { userName: _userName, ...userData } = formData

    // 先创建用户
    const result = await addUser(scriptId)
    if (result && result.userId) {
      userId = result.userId
      isEdit.value = true

      // 再更新用户数据
      const success = await updateUser(scriptId, userId, userData)
      if (success) {
        message.success('添加成功')
        router.push('/scripts')
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存用户失败: ${errorMsg}`)
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
      message.error('创建用户失败')
      router.push('/scripts')
    }
    // 标记初始化完成
    isInitializing.value = false
  })
}
</script>

<style scoped>
.user-edit-container {
  padding: var(--v6-space-8);
  min-height: 100vh;
  background: var(--v6-color-window);
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

.config-form :deep(.form-section) {
  min-width: 0;
  margin: 0 0 var(--v6-space-4);
  padding: var(--v6-space-5);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: var(--v6-vibrancy-content);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: blur(24px) saturate(1.18);
  -webkit-backdrop-filter: blur(24px) saturate(1.18);
  break-inside: avoid;
}

/* 宽容器：iPad 设置式双栏瀑布流。卡片在两列内各自纵向堆叠、互不等高拉伸；
   前两张卡（基本信息 / 关卡）保持通栏。窄容器回落为上方的单列堆叠。 */
@container app-content (min-width: 981px) {
  .config-form {
    columns: 2;
    column-gap: var(--v6-space-4);
  }

  .config-form :deep(.form-section) {
    display: inline-block;
    width: 100%;
    vertical-align: top;
  }

  .config-form :deep(.form-section:nth-child(1)),
  .config-form :deep(.form-section:nth-child(2)) {
    display: block;
    column-span: all;
  }
}

.config-form :deep(.section-header) {
  margin-bottom: var(--v6-space-4);
  padding-bottom: var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.config-form :deep(.section-header h3) {
  font-size: var(--v6-font-size-lg);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
}

.config-form :deep(.section-header h3::before) {
  display: none;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .user-edit-container {
    padding: var(--v6-space-4);
  }

  .user-edit-content {
    max-width: 100%;
  }

  .config-form :deep(.form-section) {
    padding: var(--v6-space-4);
  }

  .config-form :deep(.form-section .ant-col) {
    flex: 0 0 100%;
    max-width: 100%;
  }
}

[data-perf-mode='low'] .config-form :deep(.form-section) {
  background: var(--v6-color-surface);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

/* SRC 配置遮罩样式（与 MAA 一致） */
.src-config-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: color-mix(in srgb, #000 45%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--v6-z-modal-backdrop);
}

.mask-content {
  background: var(--v6-color-surface-elevated);
  border-radius: var(--v6-radius-md);
  padding: var(--v6-space-6);
  max-width: 480px;
  width: 100%;
  text-align: center;
  box-shadow: var(--v6-shadow-elevated);
  border: 1px solid var(--v6-color-border);
}

.mask-icon {
  margin-bottom: var(--v6-space-4);
}

.mask-title {
  font-size: var(--v6-font-size-xl);
  font-weight: var(--v6-font-weight-semibold);
  margin: 0 0 var(--v6-space-2);
  color: var(--v6-color-text);
}

.mask-description {
  font-size: var(--v6-font-size-base);
  color: var(--v6-color-text-secondary);
  margin: 0 0 var(--v6-space-6);
  line-height: var(--v6-line-height-normal);
}

.mask-actions {
  display: flex;
  justify-content: center;
}
</style>
