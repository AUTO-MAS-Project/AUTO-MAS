<template>
  <div class="user-edit-container">
    <div class="user-edit-header">
      <div class="header-nav">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts">脚本管理</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>{{ scriptName || '通用脚本' }}</a-breadcrumb-item>
        </a-breadcrumb>
        <h1>{{ isEdit ? '编辑通用用户' : '添加通用用户' }}</h1>
        <p>基本信息、额外脚本与通知配置会在操作后即时保存</p>
      </div>

      <a-space size="small" wrap>
        <a-button
          v-if="!showGeneralConfigMask"
          type="primary"
          ghost
          :loading="generalConfigLoading"
          @click="handleGeneralConfig"
        >
          <template #icon>
            <SettingOutlined />
          </template>
          通用配置
        </a-button>
        <a-tag v-else color="processing">正在配置</a-tag>
        <a-button class="cancel-button" @click="handleCancel">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          返回
        </a-button>
      </a-space>
    </div>

    <!-- 通用配置遮罩层 -->
    <teleport to="body">
      <div v-if="showGeneralConfigMask" class="maa-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: 'var(--v6-color-info)' }" />
          </div>
          <h2 class="mask-title">正在进行通用配置</h2>
          <p class="mask-description">
            当前正在进行该用户的通用配置，请在配置界面完成相关设置。
            <br />
            配置完成后，请点击“保存配置”结束配置会话。
          </p>
          <div class="mask-actions">
            <a-button
              v-if="generalWebsocketId"
              type="primary"
              size="large"
              @click="handleSaveGeneralConfig"
            >
              保存配置
            </a-button>
          </div>
        </div>
      </div>
    </teleport>

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
          <!-- 基本信息 -->
          <div class="form-section">
            <div class="section-header">
              <h3>基本信息</h3>
            </div>
            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item name="userName" required>
                  <template #label>
                    <a-tooltip title="用于识别用户的显示名称">
                      <span class="form-label">
                        用户名
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="formData.userName"
                    placeholder="请输入用户名"
                    :disabled="loading"
                    size="large"
                    class="modern-input"
                    @blur="handleFieldSave('userName', formData.userName)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item name="status">
                  <template #label>
                    <a-tooltip title="是否启用该用户">
                      <span class="form-label">
                        启用状态
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
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
                <a-form-item name="remainedDay">
                  <template #label>
                    <a-tooltip title="账号剩余的有效天数，「-1」表示无限">
                      <span class="form-label">
                        剩余天数
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
              <a-col :span="12">
                <!-- 占位列 -->
              </a-col>
            </a-row>

            <a-form-item name="notes">
              <template #label>
                <a-tooltip title="为用户添加备注信息">
                  <span class="form-label">
                    备注
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-textarea
                v-model:value="formData.Info.Notes"
                placeholder="请输入备注信息"
                :rows="4"
                :disabled="loading"
                class="modern-input"
                @blur="handleFieldSave('Info.Notes', formData.Info.Notes)"
              />
            </a-form-item>
          </div>

          <!-- 额外脚本 -->
          <ExtraScriptSection :form-data="formData" :loading="loading" @save="handleFieldSave" />

          <!-- 通知配置 -->
          <div class="form-section">
            <div class="section-header">
              <h3>通知配置</h3>
            </div>
            <a-row :gutter="24" align="middle">
              <a-col :span="6">
                <span style="font-weight: 500">启用通知</span>
              </a-col>
              <a-col :span="18">
                <a-switch
                  v-model:checked="formData.Notify.Enabled"
                  :disabled="loading"
                  @change="handleFieldSave('Notify.Enabled', formData.Notify.Enabled)"
                />
                <span class="switch-description">启用后将发送任务通知</span>
              </a-col>
            </a-row>

            <!-- 发送统计 -->
            <a-row :gutter="24" style="margin-top: 16px">
              <a-col :span="6">
                <span style="font-weight: 500">通知内容</span>
              </a-col>
              <a-col :span="18">
                <a-checkbox
                  v-model:checked="formData.Notify.IfSendStatistic"
                  :disabled="loading || !formData.Notify.Enabled"
                  @change="
                    handleFieldSave('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)
                  "
                  >统计信息
                </a-checkbox>
              </a-col>
            </a-row>

            <!-- 邮件通知 -->
            <a-row :gutter="24" style="margin-top: 16px">
              <a-col :span="6">
                <a-checkbox
                  v-model:checked="formData.Notify.IfSendMail"
                  :disabled="loading || !formData.Notify.Enabled"
                  @change="handleFieldSave('Notify.IfSendMail', formData.Notify.IfSendMail)"
                  >邮件通知
                </a-checkbox>
              </a-col>
              <a-col :span="18">
                <a-input
                  v-model:value="formData.Notify.ToAddress"
                  placeholder="请输入收件人邮箱地址"
                  :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfSendMail"
                  size="large"
                  style="width: 100%"
                  @blur="handleFieldSave('Notify.ToAddress', formData.Notify.ToAddress)"
                />
              </a-col>
            </a-row>

            <!-- Server酱通知 -->
            <a-row :gutter="24" style="margin-top: 16px">
              <a-col :span="6">
                <a-checkbox
                  v-model:checked="formData.Notify.IfServerChan"
                  :disabled="loading || !formData.Notify.Enabled"
                  @change="handleFieldSave('Notify.IfServerChan', formData.Notify.IfServerChan)"
                  >Server酱
                </a-checkbox>
              </a-col>
              <a-col :span="18">
                <div class="sensitive-field">
                  <a-input-password
                    :value="serverChanKeyDraft"
                    :placeholder="serverChanKeyPlaceholder"
                    autocomplete="new-password"
                    :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfServerChan"
                    size="large"
                    style="width: 100%"
                    @update:value="serverChanKeyDraft = $event"
                  />
                  <div class="sensitive-actions">
                    <span class="sensitive-hint">原值不会回显；留空保持原值</span>
                    <a-space size="small">
                      <a-button
                        v-if="hasStoredServerChanKey"
                        danger
                        :disabled="loading"
                        @click="clearServerChanKey"
                      >
                        清空原值
                      </a-button>
                      <a-button
                        type="primary"
                        :disabled="loading || !serverChanKeyDraft"
                        @click="saveServerChanKey"
                      >
                        保存新值
                      </a-button>
                    </a-space>
                  </div>
                </div>
              </a-col>
            </a-row>

            <!-- 自定义 Webhook 通知 -->
            <div style="margin-top: 16px">
              <WebhookManager
                mode="user"
                :script-id="scriptId"
                :user-id="userId"
                @change="handleWebhookChange"
              />
            </div>
          </div>
        </a-form>
      </a-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { useWebSocket } from '@/composables/useWebSocket.ts'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn.ts'
import WebhookManager from '@/components/WebhookManager.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'

const logger = window.electronAPI.getLogger('通用用户编辑')

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
const serverChanKeyDraft = ref('')
const hasStoredServerChanKey = ref(false)
const serverChanKeyPlaceholder = computed(() =>
  hasStoredServerChanKey.value ? '已保存；输入新值后明确保存' : '请输入 SENDKEY'
)

// 路由参数
const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId) // 使用 ref 以便在创建后更新

// 脚本信息
const scriptName = ref('')

// 通用配置相关
const generalConfigLoading = ref(false)
const generalSubscriptionId = ref<string | null>(null)
const generalWebsocketId = ref<string | null>(null)
const showGeneralConfigMask = ref(false)
const configTimedOut = ref(false) // 新增：标记是否已超时
let generalConfigTimeout: number | null = null

// 通用脚本默认用户数据
const getDefaultGeneralUserData = () => ({
  Info: {
    Name: '',
    Notes: '',
    Status: true,
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    IfScriptAfterTask: false,
    ScriptBeforeTask: '',
    ScriptAfterTask: '',
  },
  Notify: {
    Enabled: false,
    ToAddress: '',
    IfSendMail: false,
    IfSendStatistic: false,
    IfServerChan: false,
    ServerChanKey: '',
    ServerChanChannel: '',
    ServerChanTag: '',
    CustomWebhooks: [],
  },
  Data: {
    LastProxyDate: '2000-01-01',
    ProxyTimes: 0,
  },
})

// 创建扁平化的表单数据，用于表单验证
const formData = reactive({
  // 扁平化的验证字段
  userName: '',
  // 嵌套的实际数据
  ...getDefaultGeneralUserData(),
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

const updateUserOrThrow = async (userData: Record<string, unknown>) => {
  const saved = await updateUser(scriptId, userId, userData)
  if (saved === false) {
    throw new Error('用户配置更新未成功')
  }
}

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

// 即时保存单个字段变更
const handleFieldSave = async (key: string, value: any) => {
  if (isInitializing.value || isSaving.value || !userId) return

  isSaving.value = true
  saveError.value = ''
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

    await updateUserOrThrow(userData)
    // 刷新数据
    await loadUserData()
    logger.info(`用户配置已保存: ${key}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
    saveError.value = `保存失败：${errorMsg}`
  } finally {
    isSaving.value = false
  }
}

// 保存完整用户数据（仅用于特殊批量操作）
const _saveFullUserData = async () => {
  if (isInitializing.value || isSaving.value || !userId) return

  isSaving.value = true
  try {
    formData.Info.Name = formData.userName
    const notifyData: Partial<typeof formData.Notify> = { ...formData.Notify }
    delete notifyData.ServerChanKey
    const userData = {
      Info: { ...formData.Info },
      Notify: notifyData,
      Data: { ...formData.Data },
    }

    await updateUserOrThrow(userData)
    logger.info('用户配置已保存')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
    saveError.value = `保存失败：${errorMsg}`
  } finally {
    isSaving.value = false
  }
}

// 注意：移除了 watch 自动保存，现在由各控件的 @change/@blur 事件触发保存

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
      message.error('脚本不存在')
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
    message.error('加载脚本信息失败')
  }
}

// 新增模式下立即创建用户
const createUserImmediately = async () => {
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

// 加载用户数据
const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)

    if (userResponse && userResponse.code === 200) {
      // 查找指定的用户数据
      const userIndex = userResponse.index.find(index => index.uid === userId)
      if (userIndex && userResponse.data[userId]) {
        const userData = userResponse.data[userId] as any

        // 填充通用用户数据
        if (userIndex.type === 'GeneralUserConfig') {
          hasStoredServerChanKey.value = Boolean(userData.Notify?.ServerChanKey)
          Object.assign(formData, {
            Info: { ...getDefaultGeneralUserData().Info, ...userData.Info },
            Notify: {
              ...getDefaultGeneralUserData().Notify,
              ...userData.Notify,
              ServerChanKey: '',
            },
            Data: { ...getDefaultGeneralUserData().Data, ...userData.Data },
          })
          serverChanKeyDraft.value = ''
        }

        // 同步扁平化字段 - 使用nextTick确保数据更新完成后再同步
        await nextTick()
        formData.userName = formData.Info.Name || ''

        logger.info('用户数据加载成功')

        // 数据加载完成，允许自动保存
        isInitializing.value = false
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

const saveServerChanKey = async () => {
  if (!serverChanKeyDraft.value || isSaving.value || !userId) return
  isSaving.value = true
  saveError.value = ''
  try {
    await updateUserOrThrow({ Notify: { ServerChanKey: serverChanKeyDraft.value } })
    serverChanKeyDraft.value = ''
    hasStoredServerChanKey.value = true
    logger.info('敏感字段已保存: Notify.ServerChanKey')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    saveError.value = `Server酱密钥保存失败：${errorMsg}`
    logger.error(`敏感字段保存失败: Notify.ServerChanKey: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const clearServerChanKey = () => {
  Modal.confirm({
    title: '清空 Server酱密钥',
    content: '清空后无法恢复，确定继续吗？',
    okText: '清空',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      if (isSaving.value || !userId) return
      isSaving.value = true
      saveError.value = ''
      try {
        await updateUserOrThrow({ Notify: { ServerChanKey: '' } })
        serverChanKeyDraft.value = ''
        hasStoredServerChanKey.value = false
        logger.info('敏感字段已清空: Notify.ServerChanKey')
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        saveError.value = `Server酱密钥清空失败：${errorMsg}`
        logger.error(`敏感字段清空失败: Notify.ServerChanKey: ${errorMsg}`)
        throw error
      } finally {
        isSaving.value = false
      }
    },
  })
}

const handleGeneralConfig = async () => {
  try {
    generalConfigLoading.value = true

    // 先立即显示遮罩以避免后端延迟导致无法感知
    showGeneralConfigMask.value = true

    // 如果已有连接，先断开并清理
    if (generalSubscriptionId.value) {
      unsubscribe(generalSubscriptionId.value)
      generalSubscriptionId.value = null
      generalWebsocketId.value = null
      showGeneralConfigMask.value = false
      configTimedOut.value = false
      if (generalConfigTimeout) {
        window.clearTimeout(generalConfigTimeout)
        generalConfigTimeout = null
      }
    }

    // 调用后端启动任务接口，传入 userId 作为 taskId 与设置模式
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: userId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })

    logger.debug(`通用配置 start 接口返回: ${response}`)
    if (response && response.taskId) {
      const wsId = response.taskId

      logger.debug(`订阅 websocketId: ${wsId}`)

      // 订阅 websocket
      const subscriptionId = subscribe({ id: wsId }, (wsMessage: any) => {
        if (wsMessage.type === 'error') {
          logger.error(`用户 ${formData.userName} 通用配置错误: ${wsMessage.data}`)
          message.error(`通用配置连接失败: ${wsMessage.data}`)
          unsubscribe(subscriptionId)
          generalSubscriptionId.value = null
          generalWebsocketId.value = null
          showGeneralConfigMask.value = false
          configTimedOut.value = false
          if (generalConfigTimeout) {
            window.clearTimeout(generalConfigTimeout)
            generalConfigTimeout = null
          }
          return
        }

        // 处理Info类型的错误消息（显示错误但不取消订阅，等待Signal消息）
        if (wsMessage.type === 'Info' && wsMessage.data && wsMessage.data.Error) {
          logger.error(`用户 ${formData.userName} 通用配置异常: ${wsMessage.data.Error}`)
          message.error(`通用配置失败: ${wsMessage.data.Error}`)
          // 不取消订阅，等待Signal类型的Accomplish消息
          return
        }

        // 处理任务结束消息（Signal类型且包含Accomplish字段）
        if (
          wsMessage.type === 'Signal' &&
          wsMessage.data &&
          wsMessage.data.Accomplish !== undefined
        ) {
          logger.info(`用户 ${formData.userName} 通用配置任务已结束`)
          // 根据结果显示不同消息
          const result = wsMessage.data.Accomplish
          if (result && !result.includes('异常') && !result.includes('错误')) {
            message.success(`用户 ${formData.userName} 的配置已完成`)
          }
          // 清理连接
          unsubscribe(subscriptionId)
          generalSubscriptionId.value = null
          generalWebsocketId.value = null
          showGeneralConfigMask.value = false
          configTimedOut.value = false
          if (generalConfigTimeout) {
            window.clearTimeout(generalConfigTimeout)
            generalConfigTimeout = null
          }
        }
      })

      generalSubscriptionId.value = subscriptionId
      generalWebsocketId.value = wsId
      showGeneralConfigMask.value = true
      configTimedOut.value = false
      message.success(`已开始配置用户 ${formData.userName} 的通用设置`)

      // 设置 30 分钟超时自动断开
      generalConfigTimeout = window.setTimeout(
        async () => {
          if (generalSubscriptionId.value && generalWebsocketId.value) {
            // 超时后自动保存配置
            message.warning(
              `用户 ${formData.userName} 的配置会话已超时（30分钟），正在自动保存配置...`
            )
            logger.warn('配置会话已超时，自动执行保存操作')

            try {
              const websocketId = generalWebsocketId.value
              const response = await Service.stopTaskApiDispatchStopPost({ taskId: websocketId })

              if (response && response.code === 200) {
                if (generalSubscriptionId.value) {
                  unsubscribe(generalSubscriptionId.value)
                  generalSubscriptionId.value = null
                }
                generalWebsocketId.value = null
                showGeneralConfigMask.value = false
                configTimedOut.value = false
                message.success('配置会话超时，已自动保存配置')
              } else {
                message.error(response?.message || '自动保存配置失败，请手动保存')
              }
            } catch (error) {
              const errorMsg = error instanceof Error ? error.message : String(error)
              logger.error(`超时自动保存配置失败: ${errorMsg}`)
              message.error('自动保存配置失败，请手动保存')
              // 失败时保留按钮让用户手动操作
              configTimedOut.value = true
            }
          }
          generalConfigTimeout = null
        },
        30 * 60 * 1000
      )
    } else {
      message.error(response?.message || '启动通用配置失败')
      showGeneralConfigMask.value = false
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动通用配置失败: ${errorMsg}`)
    message.error('启动通用配置失败')
    showGeneralConfigMask.value = false
  } finally {
    generalConfigLoading.value = false
  }
}

const handleSaveGeneralConfig = async () => {
  try {
    const websocketId = generalWebsocketId.value
    if (!websocketId) {
      message.error('未找到活动的配置会话')
      return
    }

    const response = await Service.stopTaskApiDispatchStopPost({ taskId: websocketId })
    if (response && response.code === 200) {
      if (generalSubscriptionId.value) {
        unsubscribe(generalSubscriptionId.value)
        generalSubscriptionId.value = null
      }
      generalWebsocketId.value = null
      showGeneralConfigMask.value = false
      configTimedOut.value = false
      if (generalConfigTimeout) {
        window.clearTimeout(generalConfigTimeout)
        generalConfigTimeout = null
      }
      message.success('用户的通用配置已保存')
    } else {
      message.error(response.message || '保存配置失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存通用配置失败: ${errorMsg}`)
    message.error('保存通用配置失败')
  }
}

// 处理 Webhook 变化
const handleWebhookChange = () => {
  // Webhook 有自己的保存逻辑，这里只记录日志
  logger.info(`User webhooks changed: ${JSON.stringify(formData.Notify.CustomWebhooks)}`)
}

const handleCancel = () => {
  if (generalSubscriptionId.value) {
    unsubscribe(generalSubscriptionId.value)
    generalSubscriptionId.value = null
    generalWebsocketId.value = null
    showGeneralConfigMask.value = false
    configTimedOut.value = false
    if (generalConfigTimeout) {
      window.clearTimeout(generalConfigTimeout)
      generalConfigTimeout = null
    }
  }
  router.push('/scripts')
}

onMounted(() => {
  if (!scriptId) {
    message.error('缺少脚本ID参数')
    handleCancel()
    return
  }

  loadScriptInfo()
})
</script>

<style scoped>
.user-edit-container {
  min-height: 100vh;
  padding: var(--v6-space-8);
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

.header-nav {
  flex: 1;
}

.breadcrumb {
  margin: 0 0 var(--v6-space-2);
  font-size: var(--v6-font-size-sm);
}

.header-nav h1 {
  margin: 0;
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-3xl);
  font-weight: var(--v6-font-weight-semibold);
  line-height: var(--v6-line-height-tight);
  letter-spacing: -0.02em;
}

.header-nav p {
  margin: var(--v6-space-1) 0 0;
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-base);
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
   首张卡（基本信息）保持通栏。窄容器回落为上方的单列堆叠。 */
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

  .form-section:first-child {
    display: block;
    column-span: all;
  }
}

.section-header {
  margin-bottom: var(--v6-space-4);
  padding-bottom: var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.section-header h3 {
  margin: 0;
  font-size: var(--v6-font-size-lg);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
}

.section-header h3::before {
  display: none;
}

.form-label {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-base);
}

.help-icon {
  color: var(--v6-color-text-tertiary);
  font-size: var(--v6-font-size-base);
  cursor: help;
  transition: color var(--v6-motion-fast) var(--v6-ease-out);
}

.help-icon:hover {
  color: var(--v6-color-info);
}

.modern-input {
  border-radius: var(--v6-radius-md);
  border: 2px solid var(--v6-color-border);
  background: var(--v6-color-surface);
  transition: all var(--v6-motion-fast) var(--v6-ease-out);
}

.modern-input:hover {
  border-color: color-mix(in srgb, var(--v6-color-info) 80%, #000 20%);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--v6-color-info);
  box-shadow: var(--v6-shadow-focus-ring);
}

.switch-description {
  margin-left: var(--v6-space-3);
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text-secondary);
}

.cancel-button {
  border: 1px solid var(--v6-color-border);
  background: var(--v6-vibrancy-content);
  color: var(--v6-color-text);
  backdrop-filter: blur(18px) saturate(1.15);
}

.cancel-button:hover {
  border-color: var(--v6-color-info);
  color: var(--v6-color-info);
}

.sensitive-field {
  display: grid;
  gap: var(--v6-space-2);
}

.sensitive-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-3);
}

.sensitive-hint {
  color: var(--v6-color-text-tertiary);
  font-size: var(--v6-font-size-sm);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .user-edit-header {
    flex-direction: column;
    gap: var(--v6-space-4);
    align-items: stretch;
  }

  .user-edit-content {
    max-width: 100%;
  }

  .user-edit-container {
    padding: var(--v6-space-4);
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

/* 通用/MAA 配置遮罩样式（用于全局覆盖） */
.maa-config-mask {
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
