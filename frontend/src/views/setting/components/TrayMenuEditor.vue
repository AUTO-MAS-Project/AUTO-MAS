<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Modal, message, type TableColumnsType } from 'ant-design-vue'
import {
  DeleteOutlined,
  DownOutlined,
  QuestionCircleOutlined,
  UpOutlined,
} from '@ant-design/icons-vue'
import { Service } from '@/api/services/Service'
import {
  DEFAULT_TRAY_ITEMS,
  TRAY_ACTION_OPTIONS,
  type TrayAction,
  type TrayMenuItem,
} from '@/types/tray'

interface TaskOption {
  label: string
  value: string
}

const { t } = useI18n()

const items = ref<TrayMenuItem[]>([])
const actionOptions = TRAY_ACTION_OPTIONS
// 可启动的任务列表（队列 + 未锁定的脚本），供「启动任务」动作选择
const taskOptions = ref<TaskOption[]>([])
const logger = window.electronAPI?.getLogger?.('托盘菜单')

const columns = computed<TableColumnsType>(() => [
  { title: t('setting.tray.colLabel'), key: 'label', width: 240 },
  { title: t('setting.tray.colAction'), key: 'action', width: 260 },
  { title: t('setting.tray.colOps'), key: 'ops', width: 140, align: 'center' },
])

let persistTimer: ReturnType<typeof setTimeout> | null = null

const createId = () =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `tray-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

const labelOf = (action: TrayAction) =>
  actionOptions.find(option => option.value === action)?.label ?? ''

const taskLabelOf = (taskId?: string) =>
  taskOptions.value.find(option => option.value === taskId)?.label ?? ''

const isTrayAction = (action: unknown): action is TrayAction =>
  typeof action === 'string' && actionOptions.some(option => option.value === action)

const normalizeTrayItem = (item: unknown): TrayMenuItem => {
  const savedItem = item && typeof item === 'object' ? (item as Record<string, unknown>) : {}
  const action = isTrayAction(savedItem.action) ? savedItem.action : 'show'
  const taskId =
    typeof savedItem.taskId === 'string' && savedItem.taskId.trim()
      ? savedItem.taskId.trim()
      : undefined

  return {
    id: typeof savedItem.id === 'string' && savedItem.id ? savedItem.id : createId(),
    label: typeof savedItem.label === 'string' ? savedItem.label : labelOf(action),
    action: action === 'startTask' && !taskId ? 'show' : action,
    taskId: action === 'startTask' && taskId ? taskId : undefined,
  }
}

// 标签未自定义（为空、某个动作默认名或某个任务默认名）时，跟随动作/任务自动更新
const isDefaultLabel = (label: string) =>
  !label.trim() ||
  actionOptions.some(option => option.label === label) ||
  taskOptions.value.some(option => option.label === label)

// 标签未自定义时，跟随动作更新默认名
const onActionChange = (item: TrayMenuItem, value: TrayAction) => {
  if (isDefaultLabel(item.label)) {
    item.label = labelOf(value)
  }
  if (value !== 'startTask') {
    item.taskId = undefined
  }
  schedulePersist()
}

// 选中具体任务后，标签未自定义时自动采用任务名
const onTaskChange = (item: TrayMenuItem) => {
  if (isDefaultLabel(item.label)) {
    item.label = taskLabelOf(item.taskId)
  }
  schedulePersist()
}

const load = async () => {
  try {
    const config = await window.electronAPI?.loadConfig()
    const saved = config?.UI?.TrayItems
    items.value =
      Array.isArray(saved) && saved.length ? saved.map(normalizeTrayItem) : [...DEFAULT_TRAY_ITEMS]
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger?.warn(`读取托盘菜单配置失败: ${errorMsg}`)
    items.value = [...DEFAULT_TRAY_ITEMS]
  }
}

const loadTaskOptions = async () => {
  try {
    const response = await Service.getTaskComboxApiInfoComboxTaskPost()
    if (response.code === 200) {
      // 过滤「未选择」占位项（value 为 null）
      taskOptions.value = (response.data || [])
        .filter(item => item.value)
        .map(item => ({ label: item.label, value: item.value as string }))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger?.warn(`读取可启动任务列表失败: ${errorMsg}`)
  }
}

const save = async () => {
  try {
    // items.value 是 Vue 响应式 Proxy，无法被 IPC 结构克隆，需转为普通对象再发送
    const payload = items.value.map(item => ({
      id: item.id,
      label: item.label,
      action: item.action,
      taskId: item.taskId,
    }))
    const ok = await window.electronAPI?.updateTrayConfig(payload)
    if (!ok) {
      message.error(t('setting.toast.trayMenuSaveFailed'))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger?.error(`托盘菜单保存失败: ${errorMsg}`)
    message.error(t('setting.toast.trayMenuSaveFailed'))
  }
}

// 编辑后延迟保存，避免频繁写配置与重建托盘菜单
const schedulePersist = () => {
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(() => void save(), 300)
}

const add = () => {
  items.value.push({ id: createId(), label: labelOf('show'), action: 'show' })
  schedulePersist()
}

const remove = (index: number) => {
  items.value.splice(index, 1)
  // 删除后为空时回落到默认菜单，保证托盘菜单始终可用
  if (!items.value.length) items.value = [...DEFAULT_TRAY_ITEMS]
  schedulePersist()
}

const move = (index: number, dir: -1 | 1) => {
  const target = index + dir
  if (target < 0 || target >= items.value.length) return
  const [item] = items.value.splice(index, 1)
  items.value.splice(target, 0, item)
  schedulePersist()
}

const reset = () => {
  items.value = [...DEFAULT_TRAY_ITEMS]
  void save()
}

const confirmReset = () => {
  Modal.confirm({
    title: t('setting.tray.resetTitle'),
    content: t('setting.tray.resetContent'),
    okText: t('setting.tray.reset'),
    cancelText: t('common.cancel'),
    onOk: () => {
      reset()
      message.success(t('setting.toast.trayMenuReset'))
    },
  })
}

onMounted(() => {
  void load()
  void loadTaskOptions()
})
onBeforeUnmount(() => {
  if (persistTimer) clearTimeout(persistTimer)
})
</script>

<template>
  <div class="tray-menu-editor">
    <div class="tray-menu-section-head">
      <div class="tray-menu-section-title">
        <span class="tray-menu-label">{{ t('setting.tray.section') }}</span>
        <a-tooltip :title="t('setting.tray.sectionTip')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
      </div>
      <a-space :size="8">
        <a-button size="small" @click="add">{{ t('setting.tray.add') }}</a-button>
        <a-button size="small" @click="confirmReset">{{ t('setting.tray.reset') }}</a-button>
      </a-space>
    </div>

    <div class="tray-menu-table-wrap">
      <a-table
        :columns="columns"
        :data-source="items"
        :pagination="false"
        :scroll="{ x: 640 }"
        size="small"
      >
        <template #bodyCell="{ column, record, index }">
          <a-input
            v-if="column.key === 'label'"
            v-model:value="record.label"
            size="small"
            :placeholder="t('setting.tray.colLabel')"
            :maxlength="30"
            style="width: 100%"
            @change="schedulePersist"
          />
          <div v-else-if="column.key === 'action'" class="action-cell">
            <a-select
              v-model:value="record.action"
              size="small"
              style="width: 100%"
              @change="(value: any) => onActionChange(record, value)"
            >
              <a-select-option v-for="opt in actionOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </a-select-option>
            </a-select>
            <a-select
              v-if="record.action === 'startTask'"
              v-model:value="record.taskId"
              size="small"
              style="width: 100%"
              :placeholder="t('setting.tray.taskPlaceholder')"
              show-search
              option-filter-prop="label"
              :options="taskOptions"
              @change="() => onTaskChange(record)"
            />
          </div>
          <a-space v-else-if="column.key === 'ops'" :size="4">
            <a-button
              size="small"
              type="text"
              :disabled="index === 0"
              :aria-label="t('setting.tray.moveUp')"
              @click="move(index, -1)"
            >
              <UpOutlined />
            </a-button>
            <a-button
              size="small"
              type="text"
              :disabled="index === items.length - 1"
              :aria-label="t('setting.tray.moveDown')"
              @click="move(index, 1)"
            >
              <DownOutlined />
            </a-button>
            <a-button
              size="small"
              type="text"
              danger
              :aria-label="t('setting.tray.remove')"
              @click="remove(index)"
            >
              <DeleteOutlined />
            </a-button>
          </a-space>
        </template>
      </a-table>
    </div>
  </div>
</template>

<style scoped>
.tray-menu-editor {
  margin-top: 12px;
}

.tray-menu-section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.tray-menu-section-title {
  display: flex;
  align-items: center;
  gap: 4px;
}

.tray-menu-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.help-icon {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

/* 限定宽度，避免全屏下输入框过长，降低眼动成本 */
.tray-menu-table-wrap {
  max-width: 640px;
}

.action-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
