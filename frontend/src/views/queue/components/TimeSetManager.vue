<template>
  <t-card title="定时列表" class="time-set-card">
    <!-- 顶部按钮 -->
    <template #actions>
      <t-button
        theme="primary"
        :loading="loading"
        :disabled="!props.queueId || props.queueId.trim() === ''"
        @click="addTimeSet"
      >
        <template #icon><t-icon name="add" /></template>
        添加定时
      </t-button>
    </template>

    <!-- 主表格 -->
    <t-table
      row-key="id"
      :data="timeSets"
      :columns="columns"
      drag-sort="row"
      bordered
      hover
      size="medium"
      table-layout="fixed"
      @drag-sort="onDragSort"
    >
      <!-- 状态列（Checkbox） -->
      <template #enabledSlot="{ row }">
        <t-checkbox v-model="row.enabled" @change="() => updateTimeSetStatus(row)">
          启用
        </t-checkbox>
      </template>

      <!-- 执行时间 -->
      <template #timeSlot="{ row }">
        <t-time-picker
          v-model="row.timeValue"
          format="HH:mm"
          value-type="format"
          size="medium"
          placeholder="选择时间"
          @change="() => updateTimeSetTime(row)"
        />
      </template>

      <!-- 操作 -->
      <template #actionsSlot="{ row }">
        <t-popconfirm content="确定要删除这个定时吗？" @confirm="deleteTimeSet(row.id)">
          <t-button theme="danger" variant="outline" size="small">
            <template #icon><t-icon name="delete" /></template>
            删除
          </t-button>
        </t-popconfirm>
      </template>

      <template #empty>
        <t-empty description="暂无定时任务" />
      </template>
    </t-table>
  </t-card>
</template>

<script setup lang="ts">
import { Service } from '@/api'
import { MessagePlugin } from 'tdesign-vue-next'
import { onMounted, ref, watch } from 'vue'

interface Props {
  queueId: string
  timeSets: any[]
}
const props = defineProps<Props>()
const emit = defineEmits<{ refresh: [] }>()
const loading = ref(false)
const timeSets = ref<any[]>([])

/** 初始化时间值为字符串 */
const parseTimeString = (t: string) => (t ? t : '00:00')
const formatTimeValue = (v: any) => v || '00:00'

watch(
  () => props.timeSets,
  v => {
    timeSets.value = v.map(i => ({
      ...i,
      timeValue: parseTimeString(i.time),
    }))
  },
  { deep: true, immediate: true }
)

/** 表格列 */
const columns = [
  {
    colKey: 'index',
    title: '序号',
    align: 'center',
    width: 80,
    cell: (_: any, { rowIndex }: any) => rowIndex + 1,
  },
  { colKey: 'enabled', title: '状态', align: 'center', cell: 'enabledSlot' },
  { colKey: 'time', title: '执行时间', align: 'center', cell: 'timeSlot' },
  { colKey: 'actions', title: '操作', align: 'center', cell: 'actionsSlot' },
]

/** 添加定时 */
const addTimeSet = async () => {
  if (!props.queueId?.trim()) {
    MessagePlugin.error('队列ID为空，无法添加定时')
    return
  }
  try {
    loading.value = true
    const res = await Service.addTimeSetApiQueueTimeAddPost({ queueId: props.queueId })
    if (res.code === 200 && res.timeSetId) {
      const update = await Service.updateTimeSetApiQueueTimeUpdatePost({
        queueId: props.queueId,
        timeSetId: res.timeSetId,
        data: { Info: { Enabled: false, Time: '00:00' } },
      })
      if (update.code === 200) {
        MessagePlugin.success('定时项添加成功')
        emit('refresh')
      } else MessagePlugin.error(update.message || '定时项添加失败')
    } else MessagePlugin.error(res.message || '创建定时项失败')
  } finally {
    loading.value = false
  }
}

/** 更新时间 */
const updateTimeSetTime = async (record: any) => {
  try {
    const timeString = formatTimeValue(record.timeValue)
    const res = await Service.updateTimeSetApiQueueTimeUpdatePost({
      queueId: props.queueId,
      timeSetId: record.id,
      data: { Info: { Time: timeString } },
    })
    if (res.code === 200) {
      record.time = timeString
      MessagePlugin.success('时间更新成功')
    } else {
      MessagePlugin.error(res.message || '更新失败')
      record.timeValue = record.time
    }
  } catch {
    MessagePlugin.error('网络错误')
    record.timeValue = record.time
  }
}

/** 更新状态（Checkbox切换） */
const updateTimeSetStatus = async (record: any) => {
  try {
    const res = await Service.updateTimeSetApiQueueTimeUpdatePost({
      queueId: props.queueId,
      timeSetId: record.id,
      data: { Info: { Enabled: record.enabled } },
    })
    if (res.code === 200) MessagePlugin.success(record.enabled ? '已启用' : '已禁用')
    else {
      MessagePlugin.error(res.message || '更新失败')
      record.enabled = !record.enabled
    }
  } catch {
    MessagePlugin.error('网络错误')
    record.enabled = !record.enabled
  }
}

/** 删除定时 */
const deleteTimeSet = async (id: string) => {
  try {
    const res = await Service.deleteTimeSetApiQueueTimeDeletePost({
      queueId: props.queueId,
      timeSetId: id,
    })
    if (res.code === 200) {
      MessagePlugin.success('删除成功')
      emit('refresh')
    } else MessagePlugin.error(res.message || '删除失败')
  } catch {
    MessagePlugin.error('网络错误')
  }
}

/** 拖拽排序 */
const onDragSort = async ({ newData }: any) => {
  timeSets.value = newData
  try {
    const ids = newData.map((i: any) => i.id)
    const res = await Service.reorderTimeSetApiQueueTimeOrderPost({
      queueId: props.queueId,
      indexList: ids,
    })
    if (res.code === 200) {
      MessagePlugin.success('顺序已更新')
      emit('refresh')
    } else MessagePlugin.error(res.message || '更新失败')
  } catch {
    MessagePlugin.error('排序失败')
  }
}

onMounted(() => {
  if (props.timeSets?.length) {
    timeSets.value = props.timeSets.map(i => ({
      ...i,
      timeValue: parseTimeString(i.time),
    }))
  }
})
</script>

<style scoped>
.time-set-card {
  margin-bottom: 16px;
}
.t-table {
  margin-top: 8px;
}

.t-time-picker {
  width: 100%;
}
</style>
