<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Modal, message, type FormInstance, type TableColumnsType } from 'ant-design-vue'
import { DeleteOutlined, DownOutlined, UpOutlined } from '@ant-design/icons-vue'
import {
  DEFAULT_TRAY_ITEMS,
  TRAY_ACTION_OPTIONS,
  type TrayAction,
  type TrayMenuItem,
} from '@/types/tray'
import { useTrayMenuTasks } from '@/composables/useTrayMenuTasks'

const props = defineProps<{ savedItems: TrayMenuItem[] }>()
const emit = defineEmits<{ saved: [items: TrayMenuItem[]]; close: [] }>()
const { t } = useI18n()
const logger = window.electronAPI?.getLogger?.('托盘菜单')
const {
  options: taskOptions,
  loading: tasksLoading,
  error: tasksError,
  load: loadTasks,
} = useTrayMenuTasks()
const cloneItems = (items: TrayMenuItem[]) => items.map(item => ({ ...item }))
const items = ref(cloneItems(props.savedItems))
const saving = ref(false)
const confirming = ref(false)
const form = ref<FormInstance>()
let confirmation: ReturnType<typeof Modal.confirm> | null = null
let discardPromise: Promise<boolean> | null = null
let settleDiscard: ((discard: boolean) => void) | null = null

const formModel = computed(() => ({ items: items.value }))
const dirty = computed(() => JSON.stringify(items.value) !== JSON.stringify(props.savedItems))
const locked = computed(() => saving.value || confirming.value)
const actionOptions = computed(() =>
  TRAY_ACTION_OPTIONS.map(option => ({
    ...option,
    label: t(`core.setting.tray.action.${option.value}`),
  }))
)
const columns = computed<TableColumnsType>(() => [
  { title: t('core.setting.tray.colLabel'), key: 'label', width: '32%' },
  { title: t('core.setting.tray.colAction'), key: 'action' },
  { title: t('core.setting.tray.colOps'), key: 'ops', width: 108, align: 'center' },
])

const labelOf = (action: TrayAction) =>
  TRAY_ACTION_OPTIONS.find(option => option.value === action)?.label ?? ''
const isDefaultLabel = (label: string) =>
  !label.trim() ||
  TRAY_ACTION_OPTIONS.some(option => option.label === label) ||
  actionOptions.value.some(option => option.label === label) ||
  taskOptions.value.some(option => option.label === label)

const onActionChange = (item: TrayMenuItem) => {
  if (isDefaultLabel(item.label)) item.label = labelOf(item.action)
  if (item.action !== 'startTask') item.taskId = undefined
  form.value?.clearValidate()
}

const onTaskChange = (item: TrayMenuItem) => {
  if (isDefaultLabel(item.label)) {
    item.label =
      taskOptions.value.find(option => option.value === item.taskId)?.label ?? labelOf(item.action)
  }
}

const add = () => {
  items.value.push({ id: crypto.randomUUID(), label: labelOf('show'), action: 'show' })
}

const remove = (index: number) => {
  items.value.splice(index, 1)
  // 空菜单仍恢复默认项；逐项复制，避免草稿编辑污染默认配置。
  if (!items.value.length) items.value = cloneItems(DEFAULT_TRAY_ITEMS)
  form.value?.clearValidate()
}

const move = (index: number, direction: -1 | 1) => {
  const target = index + direction
  if (target < 0 || target >= items.value.length) return
  const [item] = items.value.splice(index, 1)
  items.value.splice(target, 0, item)
  form.value?.clearValidate()
}

const reset = () => {
  items.value = cloneItems(DEFAULT_TRAY_ITEMS)
  form.value?.clearValidate()
}

const canDiscard = (): Promise<boolean> => {
  if (saving.value) return Promise.resolve(false)
  if (!dirty.value) return Promise.resolve(true)
  if (discardPromise) return discardPromise
  confirming.value = true
  discardPromise = new Promise(resolve => {
    settleDiscard = resolve
    const finish = (discard: boolean) => {
      confirming.value = false
      discardPromise = null
      settleDiscard = null
      confirmation = null
      resolve(discard)
    }
    confirmation = Modal.confirm({
      title: t('core.setting.tray.unsavedTitle'),
      content: t('core.setting.tray.unsavedContent'),
      okText: t('core.setting.tray.discard'),
      cancelText: t('core.setting.tray.continueEditing'),
      okButtonProps: { danger: true },
      autoFocusButton: 'cancel',
      onOk: () => finish(true),
      onCancel: () => finish(false),
    })
  })
  return discardPromise
}

const requestClose = async () => {
  if (await canDiscard()) emit('close')
}

const save = async () => {
  if (locked.value) return
  saving.value = true
  try {
    await form.value?.validate()
  } catch {
    saving.value = false
    return
  }
  // 只发送普通对象，避免 Vue Proxy 无法通过 IPC 结构克隆。
  const payload = cloneItems(items.value)
  try {
    const ok = await window.electronAPI?.updateTrayConfig(payload)
    if (!ok) throw new Error('托盘菜单未保存')
    message.success(t('core.setting.tray.saved'))
    emit('saved', payload)
  } catch (error) {
    logger?.error(`保存托盘菜单失败: ${error instanceof Error ? error.message : String(error)}`)
    message.error(t('core.setting.toast.trayMenuSaveFailed'))
  } finally {
    saving.value = false
  }
}

onBeforeRouteLeave(() => canDiscard())
onMounted(() => void loadTasks())
onBeforeUnmount(() => {
  settleDiscard?.(false)
  confirmation?.destroy()
})
</script>

<template>
  <a-modal
    :open="true"
    :title="t('core.setting.tray.editTitle')"
    :width="760"
    wrap-class-name="tray-menu-dialog"
    :closable="!locked"
    :mask-closable="!locked"
    :keyboard="!locked"
    @cancel="requestClose"
  >
    <p class="tray-editor-hint">{{ t('core.setting.tray.editorHint') }}</p>
    <a-alert
      v-if="tasksError"
      type="warning"
      show-icon
      class="tray-tasks-error"
      :message="tasksError"
    >
      <template #action>
        <a-button size="small" :disabled="locked" :loading="tasksLoading" @click="loadTasks">
          {{ t('core.setting.tray.retry') }}
        </a-button>
      </template>
    </a-alert>
    <a-form ref="form" :model="formModel" :disabled="locked">
      <a-table
        :columns="columns"
        :data-source="items"
        :pagination="false"
        :scroll="{ x: 580 }"
        row-key="id"
        size="small"
      >
        <template #bodyCell="{ column, record, index }">
          <a-input
            v-if="column.key === 'label'"
            v-model:value="record.label"
            :aria-label="t('core.setting.tray.colLabel')"
            :maxlength="30"
          />
          <div v-else-if="column.key === 'action'" class="tray-action-cell">
            <a-select
              v-model:value="record.action"
              :options="actionOptions"
              :aria-label="t('core.setting.tray.colAction')"
              @change="onActionChange(record)"
            />
            <a-form-item
              v-if="record.action === 'startTask'"
              :name="['items', index, 'taskId']"
              :rules="[
                { required: true, whitespace: true, message: t('core.setting.tray.taskRequired') },
              ]"
              class="tray-task-field"
            >
              <a-select
                v-model:value="record.taskId"
                :placeholder="t('core.setting.tray.taskPlaceholder')"
                :aria-label="t('core.setting.tray.taskPlaceholder')"
                :options="taskOptions"
                :loading="tasksLoading"
                :list-height="160"
                show-search
                option-filter-prop="label"
                @change="onTaskChange(record)"
              />
            </a-form-item>
          </div>
          <a-space v-else-if="column.key === 'ops'" :size="0">
            <a-button
              type="text"
              size="small"
              :disabled="locked || index === 0"
              :aria-label="t('core.setting.tray.moveUp')"
              @click="move(index, -1)"
              ><UpOutlined
            /></a-button>
            <a-button
              type="text"
              size="small"
              :disabled="locked || index === items.length - 1"
              :aria-label="t('core.setting.tray.moveDown')"
              @click="move(index, 1)"
              ><DownOutlined
            /></a-button>
            <a-button
              type="text"
              size="small"
              danger
              :disabled="locked"
              :aria-label="t('core.setting.tray.remove')"
              @click="remove(index)"
              ><DeleteOutlined
            /></a-button>
          </a-space>
        </template>
      </a-table>
    </a-form>
    <div class="tray-editor-actions">
      <a-button size="small" :disabled="locked" @click="add">{{
        t('core.setting.tray.add')
      }}</a-button>
      <a-button type="text" size="small" :disabled="locked" @click="reset">{{
        t('core.setting.tray.reset')
      }}</a-button>
    </div>
    <template #footer>
      <a-button :disabled="locked" @click="requestClose">{{ t('core.common.cancel') }}</a-button>
      <a-button type="primary" :loading="saving" :disabled="confirming || !dirty" @click="save">{{
        t('core.setting.tray.save')
      }}</a-button>
    </template>
  </a-modal>
</template>

<style scoped>
.tray-editor-hint {
  margin: 0 0 16px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.tray-tasks-error {
  margin-bottom: 16px;
}

.tray-action-cell {
  display: grid;
  gap: 8px;
}

.tray-task-field {
  margin-bottom: 0;
}

.tray-editor-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

:global(.tray-menu-dialog.ant-modal-wrap) {
  padding-block: 16px;
  overflow: hidden;
}

:global(.tray-menu-dialog .ant-modal) {
  top: 0;
  padding-bottom: 0;
}

:global(.ant-modal-root .tray-menu-dialog .ant-modal .ant-modal-content) {
  display: flex;
  flex-direction: column;
  max-height: min(560px, calc(100vh - 64px));
}

:global(.tray-menu-dialog .ant-modal-header),
:global(.tray-menu-dialog .ant-modal-footer) {
  flex-shrink: 0;
}

:global(.tray-menu-dialog .ant-modal-body) {
  min-height: 0;
  overflow-y: auto;
}
</style>
