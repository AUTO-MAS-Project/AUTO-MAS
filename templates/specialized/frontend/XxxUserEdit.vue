<template>
  <div class="user-edit-page">
    <div class="page-header">
      <a-breadcrumb>
        <a-breadcrumb-item><router-link to="/scripts">脚本管理</router-link></a-breadcrumb-item>
        <a-breadcrumb-item
          ><router-link :to="`/scripts/${scriptId}/edit/xxx`">{{
            scriptName
          }}</router-link></a-breadcrumb-item
        >
        <a-breadcrumb-item>{{ isEdit ? '编辑用户' : '添加用户' }}</a-breadcrumb-item>
      </a-breadcrumb>
      <a-space>
        <a-button type="primary" ghost :loading="configLoading" @click="startConfigSession">
          原生专项配置
        </a-button>
        <a-button @click="handleCancel">返回</a-button>
      </a-space>
    </div>

    <!-- 顶部 48px 预留给 Electron 标题栏，普通业务遮罩不覆盖窗口控制按钮。 -->
    <teleport to="body">
      <div v-if="showConfigMask" class="config-mask">
        <a-card class="mask-card">
          <h2>正在进行专项配置</h2>
          <p>请在上游配置窗口完成设置，再点击“保存配置”结束会话。</p>
          <a-space>
            <a-button
              v-if="configWebsocketId"
              type="primary"
              :loading="configStopping"
              @click="stopConfigSession(true)"
            >
              保存配置
            </a-button>
            <a-button @click="stopConfigSession(false)">关闭会话</a-button>
          </a-space>
        </a-card>
      </div>
    </teleport>

    <a-card class="config-card" :loading="pageLoading">
      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical">
        <BasicInfoSection :form-data="formData" :loading="loading" @save="handleFieldSave" />

        <!-- TODO(specialized): 添加专项用户任务 Section，并保持保存入口为 handleFieldSave。 -->

        <NotifyConfigSection
          :form-data="formData"
          :loading="loading"
          :script-id="scriptId"
          :user-id="userId"
          @save="handleFieldSave"
        />
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useRoute, useRouter } from 'vue-router'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { useWebSocket } from '@/composables/useWebSocket'
import BasicInfoSection from '../../XxxUserEdit/BasicInfoSection.vue'
import NotifyConfigSection from '../../XxxUserEdit/NotifyConfigSection.vue'

interface XxxUserFormData {
  userName: string
  Info: {
    Name: string
    Status: boolean
    RemainedDay: number
    IfUseMasConfig: boolean
    IfScriptBeforeTask: boolean
    ScriptBeforeTask: string
    IfScriptAfterTask: boolean
    ScriptAfterTask: string
    Notes: string
  }
  Data: { LastProxyDate: string; ProxyTimes: number }
  Notify: {
    Enabled: boolean
    IfSendStatistic: boolean
    IfSendMail: boolean
    ToAddress: string
    IfServerChan: boolean
    ServerChanKey: string
    CustomWebhooks: unknown[]
  }
}

const getDefaultUserData = (): XxxUserFormData => ({
  userName: '',
  Info: {
    Name: '',
    Status: true,
    RemainedDay: -1,
    IfUseMasConfig: true,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
  },
  Data: { LastProxyDate: '2000-01-01', ProxyTimes: 0 },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
    CustomWebhooks: [],
  },
})

const route = useRoute()
const router = useRouter()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()
const { subscribe, unsubscribe } = useWebSocket()
const logger = window.electronAPI.getLogger('专项用户编辑')

const scriptId = route.params.scriptId as string
let userId = (route.params.userId as string | undefined) ?? ''
const isEdit = ref(Boolean(userId))
const scriptName = ref('')
const formRef = ref<FormInstance>()
const formData = reactive<XxxUserFormData>(getDefaultUserData())
const pageLoading = ref(false)
const isInitializing = ref(true)
const isSaving = ref(false)
const loading = computed(() => userLoading.value || isSaving.value)
const rules = computed<Record<string, Rule[]>>(() => ({
  userName: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    {
      min: 1,
      max: 50,
      message: '用户名长度应在 1-50 个字符之间',
      trigger: 'blur',
    },
  ],
}))

const configLoading = ref(false)
const configStopping = ref(false)
const showConfigMask = ref(false)
const configSubscriptionId = ref<string | null>(null)
const configWebsocketId = ref<string | null>(null)
let configTimeout: number | null = null

watch(
  () => formData.Info.Name,
  value => {
    if (formData.userName !== value) formData.userName = value
  },
  { immediate: true }
)
watch(
  () => formData.userName,
  value => {
    if (formData.Info.Name !== value) formData.Info.Name = value
  }
)

const handleFieldSave = async (key: string, value: string | number | boolean) => {
  if (isInitializing.value || isSaving.value || !userId) return
  isSaving.value = true
  const parts = key.split('.')
  const userData: Record<string, Record<string, string | number | boolean>> = {}
  if (key === 'userName') {
    formData.userName = String(value)
    formData.Info.Name = String(value)
    userData.Info = { Name: value }
  } else if (parts.length === 2) {
    userData[parts[0]] = { [parts[1]]: value }
    if (parts[0] === 'Info') Object.assign(formData.Info, { [parts[1]]: value })
    if (parts[0] === 'Data') Object.assign(formData.Data, { [parts[1]]: value })
    if (parts[0] === 'Notify') Object.assign(formData.Notify, { [parts[1]]: value })
  }
  try {
    const saved = await updateUser(scriptId, userId, userData)
    if (!saved) message.error(`保存 ${key} 失败，请重试`)
  } finally {
    isSaving.value = false
  }
}

const createUserImmediately = async () => {
  const result = await addUser(scriptId)
  if (!result?.userId) {
    message.error('创建用户失败')
    await handleCancel()
    return false
  }
  userId = result.userId
  isEdit.value = true
  // 新增流程必须先创建用户，再把路由切换到带 userId 的编辑页。
  await router.replace({
    name: route.name ?? undefined,
    params: { ...route.params, userId },
  })
  return true
}

const loadUserData = async () => {
  const response = await getUsers(scriptId, userId)
  if (!response || response.code !== 200) {
    message.error('获取用户数据失败')
    return
  }
  const payload = response.data[userId] as Partial<XxxUserFormData> | undefined
  if (!payload) {
    message.error('用户不存在')
    await handleCancel()
    return
  }
  Object.assign(formData.Info, payload.Info ?? {})
  Object.assign(formData.Data, payload.Data ?? {})
  Object.assign(formData.Notify, payload.Notify ?? {})
  await nextTick()
  formData.userName = formData.Info.Name
  isInitializing.value = false
}

const loadPage = async () => {
  if (!scriptId) {
    message.error('缺少脚本 ID')
    await handleCancel()
    return
  }
  pageLoading.value = true
  try {
    const script = await getScript(scriptId)
    if (!script) {
      await handleCancel()
      return
    }
    scriptName.value = script.name
    if (!isEdit.value && !(await createUserImmediately())) return
    await loadUserData()
  } catch (error) {
    logger.error(`加载专项用户失败: ${error instanceof Error ? error.message : String(error)}`)
    message.error('加载用户页面失败')
  } finally {
    pageLoading.value = false
  }
}

const clearConfigSession = () => {
  if (configSubscriptionId.value) unsubscribe(configSubscriptionId.value)
  configSubscriptionId.value = null
  configWebsocketId.value = null
  showConfigMask.value = false
  if (configTimeout !== null) {
    window.clearTimeout(configTimeout)
    configTimeout = null
  }
}

const stopConfigSession = async (save: boolean) => {
  const websocketId = configWebsocketId.value
  if (!websocketId) {
    clearConfigSession()
    return
  }
  configStopping.value = true
  try {
    const response = await Service.stopTaskApiDispatchStopPost({
      taskId: websocketId,
    })
    if (response.code === 200) {
      clearConfigSession()
      if (save) message.success('专项配置已保存')
    } else {
      message.error(response.message || '结束专项配置失败')
    }
  } catch (error) {
    logger.error(`结束专项配置失败: ${error instanceof Error ? error.message : String(error)}`)
    message.error('结束专项配置失败')
  } finally {
    configStopping.value = false
  }
}

const startConfigSession = async () => {
  if (!userId || configLoading.value) return
  await stopConfigSession(false)
  configLoading.value = true
  showConfigMask.value = true
  try {
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: userId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })
    if (!response.taskId) throw new Error(response.message || '启动专项配置失败')
    const websocketId = response.taskId
    const subscriptionId = subscribe({ id: websocketId }, async wsMessage => {
      if (wsMessage.type === 'error') {
        message.error(`专项配置连接失败: ${String(wsMessage.data)}`)
        await stopConfigSession(false)
        return
      }
      if (wsMessage.type === 'Info' && wsMessage.data?.Error) {
        message.error(`专项配置失败: ${String(wsMessage.data.Error)}`)
        return
      }
      if (wsMessage.type === 'Signal' && wsMessage.data?.Accomplish !== undefined) {
        message.success('专项配置会话已结束')
        clearConfigSession()
      }
    })
    configSubscriptionId.value = subscriptionId
    configWebsocketId.value = websocketId
    configTimeout = window.setTimeout(
      () => {
        void stopConfigSession(true)
      },
      30 * 60 * 1000
    )
  } catch (error) {
    logger.error(`启动专项配置失败: ${error instanceof Error ? error.message : String(error)}`)
    message.error('启动专项配置失败')
    clearConfigSession()
  } finally {
    configLoading.value = false
  }
}

const handleCancel = async () => {
  await stopConfigSession(false)
  await router.push('/scripts')
}

onMounted(() => {
  void loadPage()
})
onBeforeUnmount(() => {
  void stopConfigSession(false)
})
</script>

<style scoped>
.user-edit-page {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.config-card {
  border-radius: 8px;
}

.config-mask {
  position: fixed;
  inset: 48px 0 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(0 0 0 / 45%);
}

.mask-card {
  width: min(480px, calc(100vw - 48px));
  text-align: center;
}

.mask-card h2 {
  margin: 0 0 8px;
  color: var(--ant-color-text);
  font-size: 18px;
}

.mask-card p {
  margin-bottom: 24px;
  color: var(--ant-color-text-secondary);
}
</style>
