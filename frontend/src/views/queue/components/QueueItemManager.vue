<template>
  <t-card title="任务列表" class="queue-card">
    <template #actions>
      <t-button theme="primary" :loading="loading" @click="addQueueItem">
        <template #icon><t-icon name="add" /></template>
        添加任务
      </t-button>
    </template>

    <t-table
      row-key="id"
      :data="queueItems"
      :columns="columns"
      drag-sort="row"
      table-layout="fixed"
      size="medium"
      bordered
      hover
      @drag-sort="onDragSort"
    >
      <template #script="{ row }">
        <t-select
          v-model="row.script"
          placeholder="请选择脚本"
          size="medium"
          :options="scriptOptions"
          @change="() => updateQueueItemScript(row)"
        />
      </template>

      <template #actions="{ row }">
        <t-popconfirm content="确定要删除这个任务吗？" @confirm="deleteQueueItem(row.id)">
          <t-button theme="danger" variant="outline" size="small">
            <template #icon><t-icon name="delete" /></template>
            删除
          </t-button>
        </t-popconfirm>
      </template>

      <template #empty>
        <t-empty description="暂无任务" />
      </template>
    </t-table>
  </t-card>
</template>

<script setup lang="ts">
import { Service } from '@/api'
import { MessagePlugin } from 'tdesign-vue-next'
import { onMounted, ref, watch } from 'vue'

// props
interface Props {
  queueId: string
  queueItems: any[]
}
const props = defineProps<Props>()
const emit = defineEmits<{ refresh: [] }>()

// state
const loading = ref(false)
const queueItems = ref(props.queueItems)
const scriptOptions = ref<Array<{ label: string; value: string | null }>>([])

// 监听父组件传入的变化
watch(
  () => props.queueItems,
  v => (queueItems.value = v),
  { deep: true }
)

// 列配置
const columns = [
  {
    colKey: 'index',
    title: '序号',
    width: 80,
    align: 'center',
    cell: (_: any, { rowIndex }: any) => rowIndex + 1,
  },
  { colKey: 'script', title: '脚本任务', align: 'center', cell: 'script' },
  { colKey: 'actions', title: '操作', width: 150, align: 'center', cell: 'actions' },
]

// 获取脚本下拉数据
const loadOptions = async () => {
  try {
    const res = await Service.getScriptComboxApiInfoComboxScriptPost()
    if (res.code === 200) scriptOptions.value = res.data || []
  } catch (e) {
    console.error('加载脚本失败', e)
  }
}

// 添加任务
const addQueueItem = async () => {
  try {
    loading.value = true
    const res = await Service.addItemApiQueueItemAddPost({ queueId: props.queueId })
    if (res.code === 200 && res.queueItemId) {
      MessagePlugin.success('任务添加成功')
      emit('refresh')
    } else {
      MessagePlugin.error('任务添加失败')
    }
  } finally {
    loading.value = false
  }
}

// 删除任务
const deleteQueueItem = async (id: string) => {
  try {
    const res = await Service.deleteItemApiQueueItemDeletePost({
      queueId: props.queueId,
      queueItemId: id,
    })
    if (res.code === 200) {
      MessagePlugin.success('删除成功')
      emit('refresh')
    } else {
      MessagePlugin.error('删除失败')
    }
  } catch (e) {
    MessagePlugin.error('网络错误')
  }
}

// 更新脚本
const updateQueueItemScript = async (record: any) => {
  try {
    loading.value = true
    const res = await Service.updateItemApiQueueItemUpdatePost({
      queueId: props.queueId,
      queueItemId: record.id,
      data: { Info: { ScriptId: record.script } },
    })
    if (res.code === 200) {
      MessagePlugin.success('脚本更新成功')
      emit('refresh')
    } else {
      MessagePlugin.error('脚本更新失败')
    }
  } finally {
    loading.value = false
  }
}

// 拖拽排序
const onDragSort = async ({ newData }: any) => {
  queueItems.value = newData
  try {
    const sortedIds = newData.map((i: any) => i.id)
    const res = await Service.reorderItemApiQueueItemOrderPost({
      queueId: props.queueId,
      indexList: sortedIds,
    })
    if (res.code === 200) {
      MessagePlugin.success('任务顺序已更新')
      emit('refresh')
    } else {
      MessagePlugin.error('更新失败')
    }
  } catch (e) {
    MessagePlugin.error('排序失败')
  }
}

onMounted(loadOptions)
</script>

<style scoped></style>
