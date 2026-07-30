<template>
  <div class="simple-user-edit">
    <header class="edit-header">
      <a-breadcrumb>
        <a-breadcrumb-item><router-link to="/scripts">脚本管理</router-link></a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit/simple`">{{ scriptName }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>{{ isEdit ? '编辑用户' : '添加用户' }}</a-breadcrumb-item>
      </a-breadcrumb>
      <a-button size="large" @click="router.push('/scripts')">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
    </header>

    <a-spin :spinning="loading">
      <a-card class="config-card">
        <a-form :model="formData" layout="vertical">
          <section class="form-section">
            <h3>基本信息</h3>
            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item label="用户名" required>
                  <a-input
                    v-model:value="formData.Info.Name"
                    size="large"
                    placeholder="请输入用户名"
                    @blur="saveField('Info.Name', formData.Info.Name)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="启用状态">
                  <a-select
                    v-model:value="formData.Info.Status"
                    size="large"
                    @change="saveField('Info.Status', formData.Info.Status)"
                  >
                    <a-select-option :value="true">启用</a-select-option>
                    <a-select-option :value="false">禁用</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="剩余天数">
                  <a-input-number
                    v-model:value="formData.Info.RemainedDay"
                    :min="-1"
                    :max="9999"
                    size="large"
                    style="width: 100%"
                    @change="saveField('Info.RemainedDay', formData.Info.RemainedDay)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-form-item label="备注">
              <a-textarea
                v-model:value="formData.Info.Notes"
                :rows="3"
                placeholder="请输入备注"
                @blur="saveField('Info.Notes', formData.Info.Notes)"
              />
            </a-form-item>
          </section>

          <ExtraScriptSection :form-data="formData" :loading="loading" @save="saveField" />

          <section class="form-section">
            <h3>通知配置</h3>
            <a-row :gutter="24" align="middle">
              <a-col :span="6"><span class="field-title">启用通知</span></a-col>
              <a-col :span="18">
                <a-switch
                  v-model:checked="formData.Notify.Enabled"
                  @change="saveField('Notify.Enabled', formData.Notify.Enabled)"
                />
                <span class="switch-description">启用后发送任务通知</span>
              </a-col>
            </a-row>
            <a-row :gutter="24" class="notify-row">
              <a-col :span="6"><span class="field-title">通知内容</span></a-col>
              <a-col :span="18">
                <a-checkbox
                  v-model:checked="formData.Notify.IfSendStatistic"
                  :disabled="!formData.Notify.Enabled"
                  @change="saveField('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)"
                >
                  统计信息
                </a-checkbox>
              </a-col>
            </a-row>
            <a-row :gutter="24" class="notify-row">
              <a-col :span="6">
                <a-checkbox
                  v-model:checked="formData.Notify.IfSendMail"
                  :disabled="!formData.Notify.Enabled"
                  @change="saveField('Notify.IfSendMail', formData.Notify.IfSendMail)"
                >
                  邮件通知
                </a-checkbox>
              </a-col>
              <a-col :span="18">
                <a-input
                  v-model:value="formData.Notify.ToAddress"
                  :disabled="!formData.Notify.Enabled || !formData.Notify.IfSendMail"
                  placeholder="请输入收件邮箱"
                  @blur="saveField('Notify.ToAddress', formData.Notify.ToAddress)"
                />
              </a-col>
            </a-row>
            <a-row :gutter="24" class="notify-row">
              <a-col :span="6">
                <a-checkbox
                  v-model:checked="formData.Notify.IfServerChan"
                  :disabled="!formData.Notify.Enabled"
                  @change="saveField('Notify.IfServerChan', formData.Notify.IfServerChan)"
                >
                  Server 酱
                </a-checkbox>
              </a-col>
              <a-col :span="18">
                <a-input
                  v-model:value="formData.Notify.ServerChanKey"
                  :disabled="!formData.Notify.Enabled || !formData.Notify.IfServerChan"
                  placeholder="请输入 SENDKEY"
                  @blur="saveField('Notify.ServerChanKey', formData.Notify.ServerChanKey)"
                />
              </a-col>
            </a-row>
            <div class="webhook-row">
              <WebhookManager
                mode="user"
                :script-id="scriptId"
                :user-id="userId"
                @change="logger.info('简易脚本用户 Webhook 已更新')"
              />
            </div>
          </section>
        </a-form>
      </a-card>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import WebhookManager from '@/components/WebhookManager.vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'

const logger = window.electronAPI.getLogger('简易脚本用户编辑')
const route = useRoute()
const router = useRouter()
const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(Boolean(userId))
const scriptName = ref('简易脚本')
const isInitializing = ref(true)
const isSaving = ref(false)

const { getScript } = useScriptApi()
const { addUser, getUsers, updateUser, loading: userLoading } = useUserApi()
const loading = computed(() => userLoading.value)

const formData = reactive({
  Info: {
    Name: '',
    Status: true,
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
    CustomWebhooks: [],
  },
  Data: {
    LastProxyDate: '2000-01-01',
    ProxyTimes: 0,
  },
})

const saveField = async (key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value || !userId) return

  const path = key.split('.')
  const data: Record<string, Record<string, unknown>> = {
    [path[0]]: { [path[1]]: value },
  }
  isSaving.value = true
  try {
    const success = await updateUser(scriptId, userId, data)
    if (!success) message.error('保存用户配置失败')
  } finally {
    isSaving.value = false
  }
}

const loadUser = async () => {
  const response = await getUsers(scriptId, userId)
  if (!response || response.code !== 200) {
    message.error('加载用户配置失败')
    return
  }

  const index = response.index.find(item => item.uid === userId)
  const user = response.data[userId]
  if (!index || String(index.type) !== 'SimpleUserConfig' || !user) {
    message.error('简易脚本用户不存在或类型不匹配')
    router.push('/scripts')
    return
  }

  Object.assign(formData.Info, user.Info)
  Object.assign(formData.Notify, user.Notify)
  Object.assign(formData.Data, user.Data)
}

const createUser = async () => {
  const result = await addUser(scriptId)
  if (!result?.userId) {
    message.error('创建用户失败')
    router.push('/scripts')
    return
  }

  userId = result.userId
  isEdit.value = true
  await router.replace({
    name: 'SimpleUserEdit',
    params: { scriptId, userId },
  })
  await loadUser()
}

const initialize = async () => {
  try {
    const script = await getScript(scriptId)
    if (!script || script.type !== 'Simple') {
      message.error('简易脚本不存在或类型不匹配')
      router.push('/scripts')
      return
    }
    scriptName.value = script.name

    if (isEdit.value) {
      await loadUser()
    } else {
      await createUser()
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error(`初始化简易脚本用户失败: ${errorMessage}`)
    message.error('初始化用户失败')
  } finally {
    isInitializing.value = false
  }
}

onMounted(initialize)
</script>

<style scoped>
.simple-user-edit {
  padding: 0 8px 32px;
}

.edit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.config-card {
  max-width: 1200px;
  margin: 0 auto;
  border-radius: 12px;
}

.form-section {
  margin-bottom: 28px;
}

.form-section:last-child {
  margin-bottom: 0;
}

.form-section h3 {
  margin: 0 0 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  color: var(--ant-color-text);
  font-size: 18px;
}

.field-title {
  font-weight: 500;
}

.switch-description {
  margin-left: 12px;
  color: var(--ant-color-text-secondary);
}

.notify-row,
.webhook-row {
  margin-top: 16px;
}
</style>
