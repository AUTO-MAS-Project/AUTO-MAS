<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit`" class="breadcrumb-link">
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
        type="primary"
        ghost
        size="large"
        @click="handleGeneralConfig"
        :loading="generalConfigLoading"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        通用配置
      </a-button>
      <a-button size="large" @click="handleCancel" class="cancel-button">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
      <a-button
        type="primary"
        size="large"
        @click="handleSubmit"
        :loading="loading"
        class="save-button"
      >
        <template #icon>
          <SaveOutlined />
        </template>
        {{ isEdit ? '保存修改' : '创建用户' }}
      </a-button>
    </a-space>
  </div>

  <div class="user-edit-content">
    <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="user-form">
      <a-card title="基本信息" class="form-card">
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
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item name="status">
              <template #label>
                <a-tooltip title="是否启用该用户">
                  <span class="form-label">
                    启用状态
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select v-model:value="formData.Info.Status" size="large">
                <a-select-option :value="true">是</a-select-option>
                <a-select-option :value="false">否</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="24">
          <a-col :span="12">
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
          />
        </a-form-item>
      </a-card>

      <a-card title="脚本配置" class="form-card">
        <a-row :gutter="24">
          <a-col :span="12">
            <a-form-item name="ifScriptBeforeTask">
              <template #label>
                <a-tooltip title="是否在任务执行前运行自定义脚本">
                  <span class="form-label">
                    任务前执行脚本
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch
                v-model:checked="formData.Info.IfScriptBeforeTask"
                :disabled="loading"
                size="default"
              />
              <span class="switch-description">启用后将在任务执行前运行指定脚本</span>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item name="ifScriptAfterTask">
              <template #label>
                <a-tooltip title="是否在任务执行后运行自定义脚本">
                  <span class="form-label">
                    任务后执行脚本
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch
                v-model:checked="formData.Info.IfScriptAfterTask"
                :disabled="loading"
                size="default"
              />
              <span class="switch-description">启用后将在任务执行后运行指定脚本</span>
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="24">
          <a-col :span="12">
            <a-form-item name="scriptBeforeTask">
              <template #label>
                <a-tooltip title="任务执行前要运行的脚本路径">
                  <span class="form-label">
                    任务前脚本
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="formData.Info.ScriptBeforeTask"
                placeholder="请输入脚本路径"
                :disabled="loading || !formData.Info.IfScriptBeforeTask"
                size="large"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item name="scriptAfterTask">
              <template #label>
                <a-tooltip title="任务执行后要运行的脚本路径">
                  <span class="form-label">
                    任务后脚本
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="formData.Info.ScriptAfterTask"
                placeholder="请输入脚本路径"
                :disabled="loading || !formData.Info.IfScriptAfterTask"
                size="large"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-card>

      <a-card title="通知配置" class="form-card">
        <a-row :gutter="24" align="middle">
          <a-col :span="6">
            <span style="font-weight: 500">启用通知</span>
          </a-col>
          <a-col :span="18">
            <a-switch v-model:checked="formData.Notify.Enabled" :disabled="loading" />
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
            />
          </a-col>
        </a-row>

        <!-- Server酱通知 -->
        <a-row :gutter="24" style="margin-top: 16px">
          <a-col :span="6">
            <a-checkbox
              v-model:checked="formData.Notify.IfServerChan"
              :disabled="loading || !formData.Notify.Enabled"
              >Server酱
            </a-checkbox>
          </a-col>
          <a-col :span="18">
            <a-input
              v-model:value="formData.Notify.ServerChanKey"
              placeholder="请输入SENDKEY"
              :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfServerChan"
              size="large"
              style="width: 100%"
            />
          </a-col>
        </a-row>

        <!-- 企业微信群机器人通知 -->
        <a-row :gutter="24" style="margin-top: 16px">
          <a-col :span="6">
            <a-checkbox
              v-model:checked="formData.Notify.IfCompanyWebHookBot"
              :disabled="loading || !formData.Notify.Enabled"
              >企业微信群机器人
            </a-checkbox>
          </a-col>
          <a-col :span="18">
            <a-input
              v-model:value="formData.Notify.CompanyWebHookBotUrl"
              placeholder="请输入机器人Webhook地址"
              :disabled="
                loading || !formData.Notify.Enabled || !formData.Notify.IfCompanyWebHookBot
              "
              size="large"
              style="width: 100%"
            />
          </a-col>
        </a-row>
      </a-card>
    </a-form>
  </div>

  <a-float-button
    type="primary"
    @click="handleSubmit"
    class="float-button"
    :style="{
      right: '24px',
    }"
  >
    <template #icon>
      <SaveOutlined />
    </template>
  </a-float-button>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  QuestionCircleOutlined,
  SaveOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useWebSocket } from '@/composables/useWebSocket'

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()
const { connect, disconnect } = useWebSocket()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)

// 路由参数
const scriptId = route.params.scriptId as string
const userId = route.params.userId as string
const isEdit = computed(() => !!userId)

// 脚本信息
const scriptName = ref('')

// 通用配置相关
const generalConfigLoading = ref(false)
const generalWebsocketId = ref<string | null>(null)

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
    IfCompanyWebHookBot: false,
    ServerChanKey: '',
    ServerChanChannel: '',
    ServerChanTag: '',
    CompanyWebHookBotUrl: '',
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

// 加载脚本信息
const loadScriptInfo = async () => {
  try {
    const script = await getScript(scriptId)
    if (script) {
      scriptName.value = script.name

      // 如果是编辑模式，加载用户数据
      if (isEdit.value) {
        await loadUserData()
      }
    } else {
      message.error('脚本不存在')
      handleCancel()
    }
  } catch (error) {
    console.error('加载脚本信息失败:', error)
    message.error('加载脚本信息失败')
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

        console.log('用户数据加载成功:', {
          userName: formData.userName,
          InfoName: formData.Info.Name,
          fullData: formData,
        })
      } else {
        message.error('用户不存在')
        handleCancel()
      }
    } else {
      message.error('获取用户数据失败')
      handleCancel()
    }
  } catch (error) {
    console.error('加载用户数据失败:', error)
    message.error('加载用户数据失败')
  }
}

const handleSubmit = async () => {
  try {
    await formRef.value?.validate()

    // 确保扁平化字段同步到嵌套数据
    formData.Info.Name = formData.userName

    console.log('提交前的表单数据:', {
      userName: formData.userName,
      InfoName: formData.Info.Name,
      isEdit: isEdit.value,
    })

    // 构建提交数据，移除通用脚本不需要的MAA专用字段
    const { IfSendSixStar, ...generalNotify } = formData.Notify
    
    const userData = {
      Info: { ...formData.Info },
      Notify: generalNotify,
      Data: { ...formData.Data },
    }

    if (isEdit.value) {
      // 编辑模式
      const result = await updateUser(scriptId, userId, userData)
      if (result) {
        message.success('用户更新成功')
        handleCancel()
      }
    } else {
      // 添加模式
      const result = await addUser(scriptId)
      if (result) {
        // 创建成功后立即更新用户数据
        try {
          const updateResult = await updateUser(scriptId, result.userId, userData)
          console.log('用户数据更新结果:', updateResult)

          if (updateResult) {
            message.success('用户创建成功')
            handleCancel()
          } else {
            message.error('用户创建成功，但数据更新失败，请手动编辑用户信息')
            // 不跳转，让用户可以重新保存
          }
        } catch (updateError) {
          console.error('更新用户数据时发生错误:', updateError)
          message.error('用户创建成功，但数据更新失败，请手动编辑用户信息')
        }
      }
    }
  } catch (error) {
    console.error('表单验证失败:', error)
  }
}

const handleGeneralConfig = async () => {
  if (!isEdit.value) {
    message.warning('请先保存用户后再进行通用配置')
    return
  }

  try {
    generalConfigLoading.value = true

    // 如果已有连接，先断开
    if (generalWebsocketId.value) {
      disconnect(generalWebsocketId.value)
      generalWebsocketId.value = null
    }

    // 建立WebSocket连接进行通用配置
    const websocketId = await connect({
      taskId: userId, // 使用用户ID进行配置
      mode: '设置脚本',
      showNotifications: true,
      onStatusChange: status => {
        console.log(`用户 ${formData.userName} 通用配置状态: ${status}`)
      },
      onMessage: data => {
        console.log(`用户 ${formData.userName} 通用配置消息:`, data)
        // 这里可以根据需要处理特定的消息
      },
      onError: error => {
        console.error(`用户 ${formData.userName} 通用配置错误:`, error)
        message.error(`通用配置连接失败: ${error}`)
        generalWebsocketId.value = null
      },
    })

    if (websocketId) {
      generalWebsocketId.value = websocketId
      message.success(`已开始配置用户 ${formData.userName} 的通用设置`)
    }
  } catch (error) {
    console.error('通用配置失败:', error)
    message.error('通用配置失败')
  } finally {
    generalConfigLoading.value = false
  }
}

const handleCancel = () => {
  // 清理WebSocket连接
  if (generalWebsocketId.value) {
    disconnect(generalWebsocketId.value)
    generalWebsocketId.value = null
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
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

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

.header-title h1 {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.subtitle {
  margin: 4px 0 0 0;
  font-size: 16px;
  color: var(--ant-color-text-secondary);
}

.user-edit-content {
  max-width: 1200px;
  margin: 0 auto;
}

.form-card {
  margin-bottom: 24px;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.form-card :deep(.ant-card-head) {
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.form-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.user-form :deep(.ant-form-item-label > label) {
  font-weight: 500;
  color: var(--ant-color-text);
}

.switch-description,
.task-description {
  margin-left: 12px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.task-description {
  display: block;
  margin-top: 4px;
  margin-left: 0;
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

/* 表单标签样式 */
.form-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.help-icon {
  font-size: 14px;
  color: var(--ant-color-text-tertiary);
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .user-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .header-title h1 {
    font-size: 24px;
  }

  .user-edit-content {
    max-width: 100%;
  }
}

.float-button {
  width: 60px;
  height: 60px;
}
</style>