<template>
  <div class="user-edit-header">
    <div class="header-title">
      <h1>{{ isEdit ? '编辑用户' : '添加用户' }}</h1>
      <p class="subtitle">{{ scriptName }}</p>
    </div>
    <a-space size="middle">
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
            <a-form-item name="userId" required>
              <template #label>
                <a-tooltip title="用户的唯一标识符，用于游戏登录">
                  <span class="form-label">
                    用户ID
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="formData.userId"
                placeholder="请输入用户ID"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="24">
          <a-col :span="12">
            <a-form-item :name="['Info', 'Password']">
              <template #label>
                <a-tooltip title="用户登录游戏的密码">
                  <span class="form-label">
                    密码
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input-password
                v-model:value="formData.Info.Password"
                placeholder="请输入密码"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item name="server">
              <template #label>
                <a-tooltip title="选择用户所在的游戏服务器">
                  <span class="form-label">
                    服务器
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="formData.Info.Server"
                placeholder="请选择服务器"
                :disabled="loading"
                :options="serverOptions"
                size="large"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="24">
          <a-col :span="8">
            <a-form-item name="medicineNumb">
              <template #label>
                <a-tooltip title="用户拥有的理智药数量，用于恢复理智">
                  <span class="form-label">
                    理智药数量
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input-number
                v-model:value="formData.Info.MedicineNumb"
                :min="0"
                :max="999"
                placeholder="0"
                :disabled="loading"
                size="large"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item name="remainedDay">
              <template #label>
                <a-tooltip title="账号剩余的有效天数">
                  <span class="form-label">
                    剩余天数
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input-number
                v-model:value="formData.Info.RemainedDay"
                :min="0"
                :max="9999"
                placeholder="0"
                :disabled="loading"
                size="large"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item name="seriesNumb">
              <template #label>
                <a-tooltip title="用户的序列号或其他标识信息">
                  <span class="form-label">
                    序列号
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="formData.Info.SeriesNumb"
                placeholder="请输入序列号"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item name="notes">
          <template #label>
            <a-tooltip title="为用户添加备注信息，便于管理和识别">
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

        <a-form-item name="status">
          <template #label>
            <a-tooltip title="启用后该用户将参与自动化任务执行">
              <span class="form-label">
                启用状态
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-switch v-model:checked="formData.Info.Status" :disabled="loading" size="default" />
          <span class="switch-description">启用后该用户将参与自动化任务</span>
        </a-form-item>
      </a-card>

      <a-card title="任务配置" class="form-card">
        <a-row :gutter="24">
          <a-col :span="8">
            <a-form-item name="ifBase">
              <template #label>
                <a-tooltip title="自动收取基建产出，包括制造站、贸易站等">
                  <span class="form-label">
                    基建
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch v-model:checked="formData.Task.IfBase" :disabled="loading" />
              <span class="task-description">自动收取基建产出</span>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item name="ifCombat">
              <template #label>
                <a-tooltip title="自动进行作战任务，包括主线、资源本等">
                  <span class="form-label">
                    作战
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch v-model:checked="formData.Task.IfCombat" :disabled="loading" />
              <span class="task-description">自动进行作战任务</span>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item name="ifMall">
              <template #label>
                <a-tooltip title="自动购买商店物品，如信用商店、采购中心等">
                  <span class="form-label">
                    商店
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch v-model:checked="formData.Task.IfMall" :disabled="loading" />
              <span class="task-description">自动购买商店物品</span>
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="24">
          <a-col :span="8">
            <a-form-item name="ifMission">
              <template #label>
                <a-tooltip title="自动完成日常任务和周常任务">
                  <span class="form-label">
                    任务
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch v-model:checked="formData.Task.IfMission" :disabled="loading" />
              <span class="task-description">自动完成日常任务</span>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item name="ifRecruiting">
              <template #label>
                <a-tooltip title="自动进行公开招募，包括刷新标签和招募干员">
                  <span class="form-label">
                    招募
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch v-model:checked="formData.Task.IfRecruiting" :disabled="loading" />
              <span class="task-description">自动进行公开招募</span>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item name="ifReclamation">
              <template #label>
                <a-tooltip title="自动进行生息演算活动任务">
                  <span class="form-label">
                    生息演算
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch v-model:checked="formData.Task.IfReclamation" :disabled="loading" />
              <span class="task-description">自动进行生息演算</span>
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="24">
          <a-col :span="8">
            <a-form-item name="ifAutoRoguelike">
              <template #label>
                <a-tooltip title="自动进行肉鸽模式，如集成战略等">
                  <span class="form-label">
                    自动肉鸽
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch v-model:checked="formData.Task.IfAutoRoguelike" :disabled="loading" />
              <span class="task-description">自动进行肉鸽模式</span>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item name="ifWakeUp">
              <template #label>
                <a-tooltip title="任务完成后唤醒设备，防止设备休眠">
                  <span class="form-label">
                    唤醒
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch v-model:checked="formData.Task.IfWakeUp" :disabled="loading" />
              <span class="task-description">任务完成后唤醒设备</span>
            </a-form-item>
          </a-col>
        </a-row>
      </a-card>

      <a-card title="通知配置" class="form-card">
        <a-row :gutter="24">
          <a-col :span="12">
            <a-form-item name="notifyEnabled">
              <template #label>
                <a-tooltip title="启用后将发送任务执行结果通知">
                  <span class="form-label">
                    启用通知
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch v-model:checked="formData.Notify.Enabled" :disabled="loading" />
              <span class="switch-description">启用后将发送任务通知</span>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item name="toAddress">
              <template #label>
                <a-tooltip title="接收通知邮件的邮箱地址">
                  <span class="form-label">
                    收件人地址
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="formData.Notify.ToAddress"
                placeholder="请输入收件人邮箱地址"
                :disabled="loading || !formData.Notify.Enabled"
                size="large"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-card>
    </a-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, SaveOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import type { User } from '@/types/script'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)

// 路由参数
const scriptId = route.params.scriptId as string
const userId = route.params.userId as string
const isEdit = computed(() => !!userId)

// 脚本信息
const scriptName = ref('')

// 服务器选项
const serverOptions = [
  { label: '官服', value: 'Official' },
  { label: 'B服', value: 'Bilibili' },
]

// 默认用户数据
const getDefaultUserData = () => ({
  Info: {
    Name: '',
    Id: '',
    Password: '',
    Server: '官服',
    MedicineNumb: 0,
    RemainedDay: 0,
    SeriesNumb: '',
    Notes: '',
    Status: true,
    Mode: 'MAA',
    InfrastMode: '默认',
    Routine: true,
    Annihilation: '当期',
    Stage: '1-7',
    StageMode: '刷完即停',
    Stage_1: '',
    Stage_2: '',
    Stage_3: '',
    Stage_Remain: '',
    IfSkland: false,
    SklandToken: '',
  },
  Task: {
    IfBase: true,
    IfCombat: true,
    IfMall: true,
    IfMission: true,
    IfRecruiting: true,
    IfReclamation: false,
    IfAutoRoguelike: false,
    IfWakeUp: false,
  },
  Notify: {
    Enabled: false,
    ToAddress: '',
    IfSendMail: false,
    IfSendSixStar: false,
    IfSendStatistic: false,
    IfServerChan: false,
    IfCompanyWebHookBot: false,
    ServerChanKey: '',
    ServerChanChannel: '',
    ServerChanTag: '',
    CompanyWebHookBotUrl: '',
  },
  Data: {
    CustomInfrastPlanIndex: '',
    IfPassCheck: false,
    LastAnnihilationDate: '',
    LastProxyDate: '',
    LastSklandDate: '',
    ProxyTimes: 0,
  },
})

// 创建扁平化的表单数据，用于表单验证
const formData = reactive({
  // 扁平化的验证字段
  userName: '',
  userId: '',
  // 嵌套的实际数据
  ...getDefaultUserData(),
})

// 表单验证规则
const rules: Record<string, Rule[]> = {
  userName: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 1, max: 50, message: '用户名长度应在1-50个字符之间', trigger: 'blur' },
  ],
  userId: [
    { required: true, message: '请输入用户ID', trigger: 'blur' },
    { min: 1, max: 50, message: '用户ID长度应在1-50个字符之间', trigger: 'blur' },
  ],
}

// 同步扁平化字段与嵌套数据
watch(
  () => formData.Info.Name,
  newVal => {
    formData.userName = newVal
  },
  { immediate: true }
)

watch(
  () => formData.Info.Id,
  newVal => {
    formData.userId = newVal
  },
  { immediate: true }
)

watch(
  () => formData.userName,
  newVal => {
    formData.Info.Name = newVal
  }
)

watch(
  () => formData.userId,
  newVal => {
    formData.Info.Id = newVal
  }
)

// 加载脚本信息
const loadScriptInfo = async () => {
  try {
    const script = await getScript(scriptId)
    if (script) {
      scriptName.value = script.name

      // 如果是编辑模式，加载用户数据
      if (isEdit.value && script.config) {
        const config = script.config as any
        if (config.SubConfigsInfo?.UserData?.instances) {
          const userInstance = config.SubConfigsInfo.UserData.instances.find(
            (instance: any) => instance.uid === userId
          )

          if (userInstance) {
            // 从用户数据中获取实际的用户信息
            const userData = config.SubConfigsInfo.UserData[userInstance.uid]
            if (userData) {
              // 填充用户数据
              Object.assign(formData, {
                Info: { ...getDefaultUserData().Info, ...userData.Info },
                Task: { ...getDefaultUserData().Task, ...userData.Task },
                Notify: { ...getDefaultUserData().Notify, ...userData.Notify },
                Data: { ...getDefaultUserData().Data, ...userData.Data },
                QFluentWidgets: {
                  ...getDefaultUserData().QFluentWidgets,
                  ...userData.QFluentWidgets,
                },
              })
              // 同步扁平化字段
              formData.userName = formData.Info.Name
              formData.userId = formData.Info.Id
            }
          }
        }
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

const handleSubmit = async () => {
  try {
    await formRef.value?.validate()

    // 构建提交数据
    const userData = {
      Info: { ...formData.Info },
      Task: { ...formData.Task },
      Notify: { ...formData.Notify },
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
        // 创建成功后更新用户数据
        await updateUser(scriptId, result.userId, userData)
        message.success('用户创建成功')
        handleCancel()
      }
    }
  } catch (error) {
    console.error('表单验证失败:', error)
  }
}

const handleCancel = () => {
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
</style>