<template>
  <a-modal
    :open="open"
    width="1180px"
    :footer="null"
    :mask-closable="false"
    :keyboard="!operationRunning"
    :z-index="900"
    :destroy-on-close="false"
    :body-style="{ padding: '0', overflow: 'hidden' }"
    class="maafw-project-manager-modal"
    title="MaaFW 项目与资源"
    @cancel="handleClose"
  >
    <MaaFWProjectManagerWorkspace
      v-if="workspaceMounted"
      :script-id="scriptId"
      scroll-container
      @converted="emit('converted', $event)"
      @refreshed="handleWorkspaceRefreshed"
      @busy-change="handleWorkspaceBusyChange"
      @operation-change="handleWorkspaceOperationChange"
    />
  </a-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Modal } from 'ant-design-vue'
import MaaFWProjectManagerWorkspace from '@/views/maafw-projects/components/MaaFWProjectManagerWorkspace.vue'

const MANAGER_CONFIRM_Z_INDEX = 950

const props = defineProps<{
  open: boolean
  scriptId: string
}>()

const emit = defineEmits<{
  'update:open': [open: boolean]
  converted: [scriptId: string]
  refreshed: []
  'busy-change': [busy: boolean]
  'operation-change': [running: boolean]
}>()

const operationRunning = ref(false)
const workspaceBusy = ref(false)
const workspaceMounted = ref(false)

watch(
  () => props.open,
  open => {
    if (open) workspaceMounted.value = true
  },
  { immediate: true }
)

const handleWorkspaceOperationChange = (running: boolean) => {
  operationRunning.value = running
  emit('operation-change', running)
  if (!running && !workspaceBusy.value && !props.open) workspaceMounted.value = false
}

const handleWorkspaceBusyChange = (busy: boolean) => {
  workspaceBusy.value = busy
  emit('busy-change', busy)
  if (!busy && !operationRunning.value && !props.open) workspaceMounted.value = false
}

const handleWorkspaceRefreshed = () => {
  emit('refreshed')
  if (!props.open && !operationRunning.value && !workspaceBusy.value) workspaceMounted.value = false
}

const handleClose = () => {
  if (!operationRunning.value) {
    emit('update:open', false)
    if (!workspaceBusy.value) workspaceMounted.value = false
    return
  }
  Modal.confirm({
    zIndex: MANAGER_CONFIRM_Z_INDEX,
    title: '操作仍在进行',
    content: '关闭窗口不会取消后端操作；完成后会自动同步向导状态，也可稍后重新打开查看。',
    okText: '仍然关闭',
    cancelText: '继续查看',
    onOk: () => emit('update:open', false),
  })
}
</script>
