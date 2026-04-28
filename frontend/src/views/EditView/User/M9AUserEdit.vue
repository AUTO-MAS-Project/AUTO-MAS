<template>
  <div class="user-edit-container">
    <M9AUserEditHeader :script-id="scriptId" :script-name="scriptName" :is-edit="isEdit" :loading="loading"
      @handle-cancel="handleCancel" />

    <div class="user-edit-content">
      <a-card class="config-card">
        <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
          <BasicInfoSection :form-data="formData" :loading="loading"
            @save="handleFieldSave" />

          <TaskQueueSection :script-id="scriptId" v-model:task-queue="taskQueue" :loading="loading" />

          <NotifyConfigSection :form-data="formData" :loading="loading" :script-id="scriptId" :user-id="userId"
            @save="handleFieldSave" />
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import type { M9ATaskQueueItem } from '@/types/script'

const logger = window.electronAPI.getLogger('M9A用户编辑')

import M9AUserEditHeader from '../../M9AUserEdit/M9AUserEditHeader.vue'
import BasicInfoSection from '../../M9AUserEdit/BasicInfoSection.vue'
import TaskQueueSection from '../../M9AUserEdit/TaskQueueSection.vue'
import NotifyConfigSection from '../../M9AUserEdit/NotifyConfigSection.vue'

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)
const isInitializing = ref(true)
const isSaving = ref(false)

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)

const scriptName = ref('')
const taskQueue = ref<M9ATaskQueueItem[]>([])



const getDefaultM9AUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    RemainedDay: -1,
    Notes: '',
    Tag: '',
  },
  Task: {
    AvailableTasks: '[]',
    Queue: '[]',
  },
  Notify: {
    Enabled: false,
    ToAddress: '',
    IfSendMail: false,
    IfSendSixStar: false,
    IfSendStatistic: false,
    IfServerChan: false,
    ServerChanKey: '',
    ServerChanChannel: '',
    ServerChanTag: '',
    CustomWebhooks: [],
  },
  Data: {
    IfPassCheck: false,
    LastProxyDate: '',
    LastSklandDate: '',
    ProxyTimes: 0,
  },
})

const formData = reactive({
  userName: '',
  ...getDefaultM9AUserData(),
})

const rules = computed(() => {
  const baseRules: Record<string, Rule[]> = {
    userName: [
      { required: true, message: '请输入用户名', trigger: 'blur' },
      { min: 1, max: 50, message: '用户名长度应在1-50个字符之间', trigger: 'blur' },
    ],
  }
  return baseRules
})

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

watch(
  () => taskQueue.value,
  newVal => {
    if (!isInitializing.value && !isSaving.value && userId) {
      handleFieldSave('Task.Queue', JSON.stringify(newVal))
    }
  },
  { deep: true }
)

const handleFieldSave = async (key: string, value: any) => {
  if (isInitializing.value || isSaving.value || !userId) return

  isSaving.value = true
  try {
    const parts = key.split('.')
    let userData: Record<string, any> = {}
    let current = userData

    for (let i = 0; i < parts.length - 1; i++) {
      current[parts[i]] = {}
      current = current[parts[i]]
    }
    current[parts[parts.length - 1]] = value

    if (key === 'userName') {
      userData = { Info: { Name: value } }
    }

    await updateUser(scriptId, userId, userData)
    logger.info(`用户配置已保存: ${key}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const loadScriptInfo = async () => {
  try {
    const script = await getScript(scriptId)
    if (script) {
      scriptName.value = script.name

      if (isEdit.value) {
        await loadUserData()
      } else {
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

const createUserImmediately = async () => {
  try {
    const result = await addUser(scriptId)
    if (result && result.userId) {
      userId = result.userId
      isEdit.value = true
      router.replace({
        name: route.name || undefined,
        params: { ...route.params, userId: result.userId },
      })
      logger.info(`用户已创建，ID: ${result.userId}`)
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

const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)

    if (userResponse && userResponse.code === 200) {
      const userIndex = userResponse.index.find(index => index.uid === userId)
      if (userIndex && userResponse.data[userId]) {
        const userData = userResponse.data[userId] as any

        if (userIndex.type === 'M9AUserConfig') {
          Object.assign(formData, {
            Info: { ...getDefaultM9AUserData().Info, ...userData.Info },
            Task: { ...getDefaultM9AUserData().Task, ...userData.Task },
            Notify: { ...getDefaultM9AUserData().Notify, ...userData.Notify },
            Data: { ...getDefaultM9AUserData().Data, ...userData.Data },
          })

          if (userData.Task?.Queue) {
            try {
              taskQueue.value = JSON.parse(userData.Task.Queue)
            } catch (e) {
              taskQueue.value = []
            }
          }
        }

        await nextTick()
        formData.userName = formData.Info.Name || ''

        logger.info('用户数据加载成功')
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

.user-edit-content {
  max-width: 1400px;
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

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .user-edit-content {
    max-width: 100%;
  }
}
</style>
