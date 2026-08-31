<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit/general`" class="breadcrumb-link">
            {{ scriptName }}
          </router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          {{ isEdit ? '编辑用户' : '添加用户' }}
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button
        v-if="!showGeneralConfigMask"
        type="primary"
        ghost
        size="large"
        :loading="generalConfigLoading"
        @click="handleGeneralConfig"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ t('edit.generalConfiguration') }}
      </a-button>
      <a-button
        v-if="showGeneralConfigMask"
        type="default"
        size="large"
        disabled
        style="color: #52c41a; border-color: #52c41a"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ t('edit.configuring') }}
      </a-button>
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        {{ t('edit.back') }}
      </a-button>
    </a-space>
  </div>

  <!-- 通用配置遮罩层 -->
  <teleport to="body">
    <div v-if="showGeneralConfigMask" class="maa-config-mask">
      <div class="mask-content">
        <div class="mask-icon">
          <SettingOutlined :style="{ fontSize: '48px', color: '#1890ff' }" />
        </div>
        <h2 class="mask-title">{{ t('edit.generalConfigurationProgress') }}</h2>
        <p class="mask-description">
          {{ t('edit.generalConfigurationThisUser') }}
          <br />
          配置完成后，请点击"保存配置"按钮来结束配置会话。
        </p>
        <div class="mask-actions">
          <a-button
            v-if="generalTaskId"
            type="primary"
            size="large"
            @click="handleSaveGeneralConfig"
          >
            {{ t('edit.saveConfiguration') }}
          </a-button>
        </div>
      </div>
    </div>
  </teleport>

  <div class="user-edit-content">
    <a-card class="config-card">
      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <!-- 基本信息 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.basicInfo') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="12">
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
            <a-col :span="6">
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
                  size="large"
                  @change="handleFieldSave('Info.Status', formData.Info.Status)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="6">
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
            <a-col :span="24">
              <GeneralConfigModeSelector
                :model-value="formData.Info.IfUseMasConfig"
                :disabled="loading"
                :saving="configModeSaving"
                @change="handleConfigModeChange"
              />
            </a-col>
          </a-row>

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
              :rows="4"
              :disabled="loading"
              class="modern-input"
              @blur="handleFieldSave('Info.Notes', formData.Info.Notes)"
            />
          </a-form-item>
        </div>

        <!-- 额外脚本 -->
        <ExtraScriptSection
          v-model:form-data="formData"
          :loading="loading"
          @save="handleFieldSave"
        />

        <!-- 通知配置 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.notificationSettings') }}</h3>
          </div>
          <a-row :gutter="24" align="middle">
            <a-col :span="6">
              <span style="font-weight: 500">{{ t('edit.enableNotifications') }}</span>
            </a-col>
            <a-col :span="18">
              <a-switch
                v-model:checked="formData.Notify.Enabled"
                :disabled="loading"
                @change="handleFieldSave('Notify.Enabled', formData.Notify.Enabled)"
              />
              <span class="switch-description">{{ t('edit.sendTaskNotificationWhen') }}</span>
            </a-col>
          </a-row>

          <!-- 发送统计 -->
          <a-row :gutter="24" style="margin-top: 16px">
            <a-col :span="6">
              <span style="font-weight: 500">{{ t('edit.notificationContent') }}</span>
            </a-col>
            <a-col :span="18">
              <a-checkbox
                v-model:checked="formData.Notify.IfSendStatistic"
                :disabled="loading || !formData.Notify.Enabled"
                @change="handleFieldSave('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)"
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
                :placeholder="t('edit.enterRecipientEmailAddress')"
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
              <a-input
                v-model:value="formData.Notify.ServerChanKey"
                :placeholder="t('edit.enterSendkey2')"
                :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfServerChan"
                size="large"
                style="width: 100%"
                @blur="handleFieldSave('Notify.ServerChanKey', formData.Notify.ServerChanKey)"
              />
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
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { useWebSocket } from '@/composables/useWebSocket.ts'
import {
  WS_TASK_COMPLETED,
  WS_TASK_NOTICE,
  type WSTaskCompletedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn.ts'
import WebhookManager from '@/components/WebhookManager.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import GeneralConfigModeSelector from './GeneralConfigModeSelector.vue'

const { t } = useI18n()

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

// 路由参数
const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId) // 使用 ref 以便在创建后更新

// 脚本信息
const scriptName = ref('')

// 通用配置相关
const generalConfigLoading = ref(false)
const configModeSaving = ref(false)
const generalSubscriptionIds = ref<string[]>([])
const generalTaskId = ref<string | null>(null)
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
    IfUseMasConfig: true,
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

// 即时保存单个字段变更
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
    // 刷新数据
    await loadUserData()
    logger.info(`用户配置已保存: ${key}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'boolean') return
  if (
    isInitializing.value ||
    configModeSaving.value ||
    !userId ||
    formData.Info.IfUseMasConfig === value
  ) {
    return
  }

  const previousValue = formData.Info.IfUseMasConfig
  formData.Info.IfUseMasConfig = value
  configModeSaving.value = true

  try {
    const saved = await updateUser(scriptId, userId, {
      Info: { IfUseMasConfig: value },
    })

    if (!saved) {
      formData.Info.IfUseMasConfig = previousValue
      return
    }

    await loadUserData()
    logger.info(`配置来源已切换为: ${value ? '用户独立配置' : '脚本直控配置'}`)
  } finally {
    configModeSaving.value = false
  }
}

// 保存完整用户数据（仅用于特殊批量操作）
const _saveFullUserData = async () => {
  if (isInitializing.value || isSaving.value || !userId) return

  isSaving.value = true
  try {
    formData.Info.Name = formData.userName
    const userData = {
      Info: { ...formData.Info },
      Notify: { ...formData.Notify },
      Data: { ...formData.Data },
    }

    await updateUser(scriptId, userId, userData)
    logger.info('用户配置已保存')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
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

        // 填充通用用户数据
        if (userIndex.type === 'GeneralUserConfig') {
          Object.assign(formData, {
            Info: { ...getDefaultGeneralUserData().Info, ...userData.Info },
            Notify: { ...getDefaultGeneralUserData().Notify, ...userData.Notify },
            Data: { ...getDefaultGeneralUserData().Data, ...userData.Data },
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

const handleGeneralConfig = async () => {
  try {
    generalConfigLoading.value = true

    // 先立即显示遮罩以避免后端延迟导致无法感知
    showGeneralConfigMask.value = true

    // 如果已有连接，先断开并清理
    if (generalSubscriptionIds.value.length > 0) {
      for (const subscriptionId of generalSubscriptionIds.value) {
        unsubscribe(subscriptionId)
      }
      generalSubscriptionIds.value = []
      generalTaskId.value = null
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

      logger.debug(`订阅 taskId: ${wsId}`)

      // 订阅 websocket
      const subscriptionIds = [
        // 处理任务提示中的错误消息（不取消订阅，等待任务结束消息）
        subscribe({ id: wsId, type: WS_TASK_NOTICE }, wsMessage => {
          const data = wsMessage.data as unknown as WSTaskNoticeData
          if (data.level === 'error') {
            logger.error(`用户 ${formData.userName} 通用配置异常: ${data.message}`)
            message.error(t('edit.generalConfigurationFailedP0', { p0: data.message }))
          }
        }),
        // 处理任务结束消息
        subscribe({ id: wsId, type: WS_TASK_COMPLETED }, wsMessage => {
          const data = wsMessage.data as unknown as WSTaskCompletedData
          logger.info(`用户 ${formData.userName} 通用配置任务已结束`)
          // 根据结果显示不同消息
          if (data.outcome === 'success') {
            message.success(t('edit.configurationUserP0Done', { p0: formData.userName }))
          }
          // 清理连接
          for (const subscriptionId of generalSubscriptionIds.value) {
            unsubscribe(subscriptionId)
          }
          generalSubscriptionIds.value = []
          generalTaskId.value = null
          showGeneralConfigMask.value = false
          configTimedOut.value = false
          if (generalConfigTimeout) {
            window.clearTimeout(generalConfigTimeout)
            generalConfigTimeout = null
          }
        }),
      ]

      generalSubscriptionIds.value = subscriptionIds
      generalTaskId.value = wsId
      showGeneralConfigMask.value = true
      configTimedOut.value = false
      message.success(t('edit.startedGeneralSetupUser', { p0: formData.userName }))

      // 设置 30 分钟超时自动断开
      generalConfigTimeout = window.setTimeout(
        async () => {
          if (generalSubscriptionIds.value.length > 0 && generalTaskId.value) {
            // 超时后自动保存配置
            message.warning(t('edit.configurationSessionUserP02', { p0: formData.userName }))
            logger.warn('配置会话已超时，自动执行保存操作')

            try {
              const taskId = generalTaskId.value
              const response = await Service.stopTaskApiDispatchStopPost({ taskId })

              if (response && response.code === 200) {
                for (const subscriptionId of generalSubscriptionIds.value) {
                  unsubscribe(subscriptionId)
                }
                generalSubscriptionIds.value = []
                generalTaskId.value = null
                showGeneralConfigMask.value = false
                configTimedOut.value = false
                message.success(t('edit.configurationSessionTimedOut'))
              } else {
                message.error(response?.message || '自动保存配置失败，请手动保存')
              }
            } catch (error) {
              const errorMsg = error instanceof Error ? error.message : String(error)
              logger.error(`超时自动保存配置失败: ${errorMsg}`)
              message.error(t('edit.automaticSaveFailedSave'))
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
    message.error(t('edit.couldNotStartGeneral'))
    showGeneralConfigMask.value = false
  } finally {
    generalConfigLoading.value = false
  }
}

const handleSaveGeneralConfig = async () => {
  try {
    const taskId = generalTaskId.value
    if (!taskId) {
      message.error(t('edit.noActiveConfigurationSession'))
      return
    }

    const response = await Service.stopTaskApiDispatchStopPost({ taskId })
    if (response && response.code === 200) {
      for (const subscriptionId of generalSubscriptionIds.value) {
        unsubscribe(subscriptionId)
      }
      generalSubscriptionIds.value = []
      generalTaskId.value = null
      showGeneralConfigMask.value = false
      configTimedOut.value = false
      if (generalConfigTimeout) {
        window.clearTimeout(generalConfigTimeout)
        generalConfigTimeout = null
      }
      message.success(t('edit.generalConfigurationThisUser2'))
    } else {
      message.error(response.message || '保存配置失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存通用配置失败: ${errorMsg}`)
    message.error(t('edit.couldNotSaveGeneral'))
  }
}

// 处理 Webhook 变化
const handleWebhookChange = () => {
  // Webhook 有自己的保存逻辑，这里只记录日志
  logger.info(`User webhooks changed: ${JSON.stringify(formData.Notify.CustomWebhooks)}`)
}

const handleCancel = () => {
  if (generalSubscriptionIds.value.length > 0) {
    for (const subscriptionId of generalSubscriptionIds.value) {
      unsubscribe(subscriptionId)
    }
    generalSubscriptionIds.value = []
    generalTaskId.value = null
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
    message.error(t('edit.missingScriptIdParameter'))
    handleCancel()
    return
  }

  loadScriptInfo()
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

.switch-description {
  margin-left: 12px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
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

.save-button {
  background: var(--ant-color-primary);
  border-color: var(--ant-color-primary);
}

.save-button:hover {
  background: var(--ant-color-primary-hover);
  border-color: var(--ant-color-primary-hover);
}

.float-button {
  width: 60px;
  height: 60px;
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

/* 通用/MAA 配置遮罩样式（用于全局覆盖） */
.maa-config-mask {
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
