<template>
  <a-card title="定时项" class="time-set-card" :loading="loading">
    <template #extra>
      <a-space>
        <a-button
          type="primary"
          @click="addTimeSet"
          :loading="loading"
          :disabled="!props.queueId || props.queueId.trim() === ''"
        >
          <template #icon>
            <PlusOutlined />
          </template>
          添加定时项
        </a-button>
      </a-space>
    </template>

    <a-table
      :columns="timeColumns"
      :data-source="timeSets"
      :pagination="false"
      size="middle"
      :scroll="{ x: 800 }"
    >
      <template #emptyText>
        <span>暂无定时项</span>
      </template>
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'enabled'">
          <a-switch
            v-model:checked="record.enabled"
            @change="updateTimeSetStatus(record)"
            size="small"
          />
        </template>
        <template v-else-if="column.key === 'time'">
          <div class="time-display">
            {{ record.time || '--:--' }}
          </div>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-space>
            <a-button size="small" @click="editTimeSet(record)">
              <EditOutlined />
              编辑
            </a-button>
            <a-popconfirm
              title="确定要删除这个定时项吗？"
              @confirm="deleteTimeSet(record.id)"
              ok-text="确定"
              cancel-text="取消"
            >
              <a-button size="small" danger>
                <DeleteOutlined />
                删除
              </a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
    </a-table>

    <!-- 定时项编辑弹窗 -->
    <a-modal
      v-model:open="modalVisible"
      :title="editingTimeSet ? '编辑定时项' : '添加定时项'"
      ok-text="确认"
      cancel-text="取消"
      @ok="saveTimeSet"
      @cancel="cancelEdit"
      :confirm-loading="saving"
    >
      <a-form ref="formRef" :model="form" :rules="rules" layout="vertical">
        <a-form-item label="执行时间" name="time">
          <a-time-picker
            v-model:value="form.time"
            format="HH:mm"
            placeholder="请选择执行时间"
            size="large"
          />
        </a-form-item>
        <a-form-item label="启用状态" name="enabled">
          <a-switch v-model:checked="form.enabled" />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-card>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { Service } from '@/api'
import type { FormInstance } from 'ant-design-vue'
import dayjs from 'dayjs'

// 时间处理工具函数
const parseTimeString = (timeStr: string) => {
  if (!timeStr) return undefined
  try {
    const [hours, minutes] = timeStr.split(':').map(Number)
    if (isNaN(hours) || isNaN(minutes)) return undefined
    return dayjs().hour(hours).minute(minutes).second(0).millisecond(0)
  } catch {
    return undefined
  }
}

const formatTimeValue = (timeValue: any) => {
  if (!timeValue) return '00:00'
  try {
    if (dayjs.isDayjs(timeValue)) {
      return timeValue.format('HH:mm')
    }
    return dayjs(timeValue).format('HH:mm')
  } catch {
    return '00:00'
  }
}

// Props
interface Props {
  queueId: string
  timeSets: any[]
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  refresh: []
}>()

// 响应式数据
const loading = ref(false)
const saving = ref(false)
const modalVisible = ref(false)
const editingTimeSet = ref<any>(null)

// 表单引用和数据
const formRef = ref<FormInstance>()
const form = reactive({
  time: undefined as any,
  enabled: true,
})

// 表单验证规则
const rules = {
  time: [{ required: true, message: '请选择执行时间', trigger: 'change' }],
}

// 表格列配置
const timeColumns = [
  {
    title: '序号',
    dataIndex: 'index',
    key: 'index',
    width: 80,
    customRender: ({ index }: { index: number }) => index + 1,
  },
  {
    title: '执行时间',
    dataIndex: 'time',
    key: 'time',
    width: 150,
  },
  {
    title: '启用状态',
    dataIndex: 'enabled',
    key: 'enabled',
    width: 100,
  },
  {
    title: '操作',
    key: 'actions',
    width: 120,
    fixed: 'right',
  },
]

// 计算属性 - 使用props传入的数据
const timeSets = ref([...props.timeSets])

// 监听props变化
watch(
  () => props.timeSets,
  newTimeSets => {
    timeSets.value = [...newTimeSets]
  },
  { deep: true, immediate: true }
)

// 刷新数据
const refreshData = () => {
  emit('refresh')
}

// 添加定时项
const addTimeSet = () => {
  editingTimeSet.value = null
  Object.assign(form, {
    time: undefined,
    enabled: true,
  })
  modalVisible.value = true
}

// 编辑定时项
const editTimeSet = (timeSet: any) => {
  editingTimeSet.value = timeSet

  // 安全地处理时间值
  const timeValue = parseTimeString(timeSet.time)

  Object.assign(form, {
    time: timeValue,
    enabled: timeSet.enabled,
  })
  modalVisible.value = true
}

// 保存定时项
const saveTimeSet = async () => {
  try {
    await formRef.value?.validate()
    saving.value = true

    // 验证queueId是否存在
    if (!props.queueId || props.queueId.trim() === '') {
      message.error('队列ID为空，无法添加定时项')
      saving.value = false
      return
    }

    // 处理时间格式 - 使用工具函数
    console.log(
      'form.time:',
      form.time,
      'type:',
      typeof form.time,
      'isDayjs:',
      dayjs.isDayjs(form.time)
    )

    const timeString = formatTimeValue(form.time)
    console.log('timeString:', timeString)

    if (editingTimeSet.value) {
      // 更新定时项
      const response = await Service.updateTimeSetApiQueueTimeUpdatePost({
        queueId: props.queueId,
        timeSetId: editingTimeSet.value.id,
        data: {
          Info: {
            Enabled: form.enabled,
            Time: timeString,
          },
        },
      })

      if (response.code === 200) {
        message.success('定时项更新成功')
      } else {
        message.error('定时项更新失败: ' + (response.message || '未知错误'))
        return
      }
    } else {
      // 添加定时项 - 先创建，再更新
      const createResponse = await Service.addTimeSetApiQueueTimeAddPost({
        queueId: props.queueId,
      })

      if (createResponse.code === 200 && createResponse.timeSetId) {
        const updateResponse = await Service.updateTimeSetApiQueueTimeUpdatePost({
          queueId: props.queueId,
          timeSetId: createResponse.timeSetId,
          data: {
            Info: {
              Enabled: form.enabled,
              Time: timeString,
            },
          },
        })

        if (updateResponse.code === 200) {
          message.success('定时项添加成功')
        } else {
          message.error('定时项添加失败: ' + (updateResponse.message || '未知错误'))
          return
        }
      } else {
        message.error('创建定时项失败: ' + (createResponse.message || '未知错误'))
        return
      }
    }

    modalVisible.value = false
    emit('refresh')
  } catch (error) {
    console.error('保存定时项失败:', error)
    message.error('保存定时项失败: ' + (error?.message || '网络错误'))
  } finally {
    saving.value = false
  }
}

// 取消编辑
const cancelEdit = () => {
  modalVisible.value = false
  editingTimeSet.value = null
}

// 更新定时项状态
const updateTimeSetStatus = async (timeSet: any) => {
  try {
    const response = await Service.updateTimeSetApiQueueTimeUpdatePost({
      queueId: props.queueId,
      timeSetId: timeSet.id,
      data: {
        Info: {
          Enabled: timeSet.enabled,
        },
      },
    })

    if (response.code === 200) {
      message.success('状态更新成功')
    } else {
      message.error('状态更新失败: ' + (response.message || '未知错误'))
      // 回滚状态
      timeSet.enabled = !timeSet.enabled
    }
  } catch (error) {
    console.error('更新状态失败:', error)
    message.error('更新状态失败: ' + (error?.message || '网络错误'))
    // 回滚状态
    timeSet.enabled = !timeSet.enabled
  }
}

// 删除定时项
const deleteTimeSet = async (timeSetId: string) => {
  try {
    const response = await Service.deleteTimeSetApiQueueTimeDeletePost({
      queueId: props.queueId,
      timeSetId,
    })

    if (response.code === 200) {
      message.success('定时项删除成功')
      // 确保删除后刷新数据
      emit('refresh')
    } else {
      message.error('删除定时项失败: ' + (response.message || '未知错误'))
    }
  } catch (error) {
    console.error('删除定时项失败:', error)
    message.error('删除定时项失败: ' + (error?.message || '网络错误'))
  }
}
</script>

<style scoped>
.time-set-card {
  margin-bottom: 24px;
}

.time-set-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}


/* 表格样式优化 */
:deep(.ant-table-tbody > tr > td) {
  padding: 12px 16px;
}

:deep(.ant-table-thead > tr > th) {
  background: var(--ant-color-fill-quaternary);
  font-weight: 600;
}

/* 时间选择器样式 */
:deep(.ant-picker) {
  width: 100%;
}

/* 开关样式 */
:deep(.ant-switch) {
  margin: 0;
}

/* 时间显示样式 */
.time-display {
  font-weight: 600;
  color: var(--ant-color-text);
  padding: 4px 8px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 4px;
  display: inline-block;
  min-width: 60px;
  text-align: center;
}
</style>