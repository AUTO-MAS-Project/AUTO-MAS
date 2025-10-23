<template>
  <t-loading :loading="loading" size="large" text="加载中，请稍候...">
    <div class="queue-main">
      <!-- 顶部标题 -->
      <div class="queue-header">
        <h1 class="page-title">调度队列</h1>
        <div class="header-actions">
          <t-space>
            <t-button theme="primary" size="large" @click="handleAddQueue">
              <template #icon><t-icon name="add" /></template>
              新建队列
            </t-button>

            <t-popconfirm
              v-if="queueList.length > 0"
              content="确定要删除这个队列吗？"
              @confirm="handleRemoveQueue(activeQueueId)"
            >
              <t-button theme="danger" variant="outline" size="large" :disabled="!activeQueueId">
                <template #icon><t-icon name="delete" /></template>
                删除当前队列
              </t-button>
            </t-popconfirm>
          </t-space>
        </div>
      </div>

      <!-- 空状态 -->
      <t-empty
        v-if="!queueList.length || !currentQueueData"
        description="暂无队列，点击“新建队列”开始"
        style="margin-top: 40px"
      />

      <!-- 主内容 -->
      <div v-else class="queue-content">
        <!-- 队列选择 -->
        <t-card>
          <template #title>
            <div class="card-title">
              <span>队列选择</span>
              <t-tag theme="success">{{ queueList.length }} 个队列</t-tag>
            </div>
          </template>
          <t-space break-line size="medium">
            <t-button
              v-for="queue in queueList"
              :key="queue.id"
              :theme="activeQueueId === queue.id ? 'primary' : 'default'"
              variant="outline"
              size="large"
              class="queue-button"
              @click="onQueueChange(queue.id)"
            >
              {{ queue.name }}
            </t-button>
          </t-space>
        </t-card>

        <!-- 队列配置 -->
        <t-card>
          <template #title>
            <div class="queue-title-container">
              <template v-if="!isEditingQueueName">
                <span class="queue-title-text">{{ currentQueueName || '队列配置' }}</span>
                <t-button theme="default" variant="text" size="small" @click="startEditQueueName">
                  <template #icon><t-icon name="edit" /></template>
                </t-button>
              </template>
              <template v-else>
                <t-input
                  v-model="currentQueueName"
                  placeholder="请输入队列名称"
                  @blur="finishEditQueueName"
                  @enter="finishEditQueueName"
                />
              </template>
            </div>
          </template>

          <!-- 队列配置项 -->
          <div class="config-row">
            <div class="config-item">
              <div class="label">
                启用状态
                <t-tooltip content="是否启用此队列"
                  ><t-icon name="help-circle" size="small"
                /></t-tooltip>
              </div>
              <t-select
                v-model="currentQueueEnabled"
                :options="enabledOptions"
                size="large"
                @change="onQueueStatusChange"
              />
            </div>

            <div class="config-item">
              <div class="label">
                启动时运行
                <t-tooltip content="软件启动时自动运行"
                  ><t-icon name="help-circle" size="small"
                /></t-tooltip>
              </div>
              <t-select
                v-model="currentStartUpEnabled"
                :options="startUpOptions"
                size="large"
                @change="onQueueSwitchChange"
              />
            </div>

            <div class="config-item">
              <div class="label">
                定时运行
                <t-tooltip content="设定时间自动运行"
                  ><t-icon name="help-circle" size="small"
                /></t-tooltip>
              </div>
              <t-select
                v-model="currentTimeEnabled"
                :options="timeOptions"
                size="large"
                @change="onQueueSwitchChange"
              />
            </div>

            <div class="config-item flex-2">
              <div class="label">
                完成后操作
                <t-tooltip content="队列完成后执行的操作"
                  ><t-icon name="help-circle" size="small"
                /></t-tooltip>
              </div>
              <t-select
                v-model="currentAfterAccomplish"
                :options="afterAccomplishOptions"
                size="large"
                @change="onAfterAccomplishChange"
              />
            </div>
          </div>

          <t-divider />

          <!-- 下方两个表格：左右各50% -->
          <div class="table-row">
            <TimeSetManager
              v-if="activeQueueId && currentQueueData"
              :queue-id="activeQueueId"
              :time-sets="currentTimeSets"
              @refresh="refreshTimeSets"
            />

            <QueueItemManager
              v-if="activeQueueId && currentQueueData"
              :queue-id="activeQueueId"
              :queue-items="currentQueueItems"
              @refresh="refreshQueueItems"
            />
          </div>
        </t-card>
      </div>
    </div>
  </t-loading>
</template>

<script setup lang="ts">
import { Service } from '@/api'
import QueueItemManager from '@/views/queue/components/QueueItemManager.vue'
import TimeSetManager from '@/views/queue/components/TimeSetManager.vue'
import { MessagePlugin } from 'tdesign-vue-next'
import { nextTick, onMounted, ref, watch } from 'vue'

const queueList = ref([])
const activeQueueId = ref('')
const currentQueueName = ref('')
const currentQueueEnabled = ref(true)
const currentStartUpEnabled = ref(false)
const currentTimeEnabled = ref(false)
const currentAfterAccomplish = ref('NoAction')
const currentTimeSets = ref([])
const currentQueueItems = ref([])
const currentQueueData = ref(null)
const isEditingQueueName = ref(false)
const loading = ref(true)

const afterAccomplishOptions = [
  { label: '无操作', value: 'NoAction' },
  { label: '退出软件', value: 'KillSelf' },
  { label: '睡眠', value: 'Sleep' },
  { label: '休眠', value: 'Hibernate' },
  { label: '关机', value: 'Shutdown' },
  { label: '强制关机', value: 'ShutdownForce' },
]
const enabledOptions = [
  { label: '启用', value: true },
  { label: '禁用', value: false },
]
const startUpOptions = [
  { label: '是', value: true },
  { label: '否', value: false },
]
const timeOptions = [
  { label: '是', value: true },
  { label: '否', value: false },
]

const fetchQueues = async () => {
  try {
    loading.value = true
    const res = await Service.getQueuesApiQueueGetPost({})
    if (res.code === 200 && res.index) {
      queueList.value = res.index.map((i: any) => ({
        id: i.uid,
        name: res.data[i.uid]?.Info?.Name || '新队列',
      }))
      if (!activeQueueId.value && queueList.value.length) {
        activeQueueId.value = queueList.value[0].id
        await nextTick()
        loadQueueData(activeQueueId.value)
      }
    }
  } finally {
    loading.value = false
  }
}

const loadQueueData = async (id: string) => {
  const res = await Service.getQueuesApiQueueGetPost({})
  currentQueueData.value = res.data[id]
  const info = currentQueueData.value?.Info || {}
  currentQueueName.value = info.Name
  currentStartUpEnabled.value = info.StartUpEnabled ?? false
  currentTimeEnabled.value = info.TimeEnabled ?? false
  currentAfterAccomplish.value = info.AfterAccomplish ?? 'NoAction'
  await refreshTimeSets()
  await refreshQueueItems()
}

const refreshTimeSets = async () => {
  const res = await Service.getTimeSetApiQueueTimeGetPost({ queueId: activeQueueId.value })
  if (res.code === 200) {
    currentTimeSets.value = res.index.map((i: any) => ({
      id: i.uid,
      time: res.data[i.uid]?.Info?.Time || '00:00',
      enabled: res.data[i.uid]?.Info?.Enabled || false,
    }))
  }
}
const refreshQueueItems = async () => {
  const res = await Service.getItemApiQueueItemGetPost({ queueId: activeQueueId.value })
  if (res.code === 200) {
    currentQueueItems.value = res.index.map((i: any) => ({
      id: i.uid,
      script: res.data[i.uid]?.Info?.ScriptId || '',
    }))
  }
}

const handleAddQueue = async () => {
  const res = await Service.addQueueApiQueueAddPost()
  if (res.code === 200 && res.queueId) {
    queueList.value.push({ id: res.queueId, name: '新队列' })
    activeQueueId.value = res.queueId
    await loadQueueData(res.queueId)
    MessagePlugin.success('队列创建成功')
  }
}
const handleRemoveQueue = async (id: string) => {
  const res = await Service.deleteQueueApiQueueDeletePost({ queueId: id })
  if (res.code === 200) {
    queueList.value = queueList.value.filter(q => q.id !== id)
    activeQueueId.value = queueList.value[0]?.id || ''
    MessagePlugin.success('队列删除成功')
  }
}
const onQueueChange = (id: string) => {
  activeQueueId.value = id
  loadQueueData(id)
}
const autoSave = async () => {
  if (!activeQueueId.value) return
  await Service.updateQueueApiQueueUpdatePost({
    queueId: activeQueueId.value,
    data: {
      Info: {
        Name: currentQueueName.value,
        StartUpEnabled: currentStartUpEnabled.value,
        TimeEnabled: currentTimeEnabled.value,
        AfterAccomplish: currentAfterAccomplish.value,
      },
    },
  })
}

watch(
  [
    currentQueueName,
    currentStartUpEnabled,
    currentTimeEnabled,
    currentAfterAccomplish,
    currentQueueEnabled,
  ],
  () => nextTick(() => autoSave()),
  { deep: true }
)

const startEditQueueName = () => (isEditingQueueName.value = true)
const finishEditQueueName = () => (isEditingQueueName.value = false)
const onQueueSwitchChange = () => autoSave()
const onAfterAccomplishChange = () => autoSave()
const onQueueStatusChange = () => autoSave()

onMounted(fetchQueues)
</script>

<style scoped>
.queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--td-text-color-primary);
}
.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

/* 四个 Select 同行排列 */
.config-row {
  display: flex;
  gap: 16px;
  align-items: flex-end;
  margin-bottom: 16px;
}
.config-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.config-item.flex-2 {
  flex: 1.5;
}
.label {
  font-size: 14px;
  font-weight: 500;
  color: var(--td-text-color-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 两个子表格并排 */
.table-row {
  display: flex;
  gap: 16px;
  margin-top: 8px;
}
.table-card {
  flex: 1;
}
</style>
