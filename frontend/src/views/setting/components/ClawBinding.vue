<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CheckCircleOutlined, QrcodeOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import type { UnwrapNestedRefs } from 'vue'
import type { useClawBinding } from '../useClawBinding'
import QQGroupCommands from './QQGroupCommands.vue'

// 提升后的绑定状态：useClawBinding 的返回值经 reactive() 包一层传入，
// 嵌套 ref 在模板里自动解包。整个对象只由 TabNotify 构造一份。
export type ClawBindingState = UnwrapNestedRefs<ReturnType<typeof useClawBinding>>

const props = defineProps<{
  binding: ClawBindingState
  // 二维码弹窗容器；通知配置弹窗场景传其 wrap 节点，其余挂 body
  getContainer?: () => HTMLElement
}>()

const { t } = useI18n()

const binding = computed(() => props.binding)

const failed = computed(() => ['expired', 'error'].includes(binding.value.state))

// 受控 popconfirm：Esc 关掉确认气泡时不让事件冒泡到弹窗根把弹窗一起关掉。
// antd popconfirm 自身的 onKeyDown 只关自己、不 stopPropagation。
const unbindConfirmOpen = ref(false)
const onEscCapture = (event: KeyboardEvent) => {
  if (!unbindConfirmOpen.value) return
  event.stopPropagation()
  unbindConfirmOpen.value = false
}
// 启停开关在配置弹窗的开关行里，这里只留绑定状态与操作
const connected = computed(() => !!binding.value.status?.connected)
const targetOptions = computed(() => [
  { value: 'c2c', label: binding.value.label('PrivateTarget') },
  { value: 'group', label: binding.value.label('GroupTarget') },
  { value: 'all', label: binding.value.label('AllTarget') },
])
const statusLabel = computed(() => {
  if (!connected.value) return binding.value.label('Unbound')
  if (binding.value.status?.state === 'reconnecting') {
    return binding.value.label('Reconnecting')
  }
  if (binding.value.status?.state === 'connecting') {
    return binding.value.label('Connecting')
  }
  return binding.value.label('Bound')
})
const statusColor = computed(() => {
  if (!connected.value) return 'default'
  return binding.value.status?.state !== 'connected' ? 'processing' : 'success'
})
let groupsTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  void binding.value.loadGroups()
  groupsTimer = setInterval(() => {
    if (connected.value && !binding.value.open) void binding.value.loadGroups()
  }, 3000)
})
onBeforeUnmount(() => clearInterval(groupsTimer))
</script>

<template>
  <div class="claw-binding" @keydown.esc.capture="onEscCapture">
    <a-typography-paragraph type="secondary" class="binding-hint">
      {{ binding.label('SetupHint') }}
    </a-typography-paragraph>
    <a-alert v-if="binding.statusError" type="error" show-icon :message="binding.statusError">
      <template #action>
        <a-button
          size="small"
          :loading="binding.statusLoading"
          :aria-label="binding.label('StatusRetry')"
          @click="binding.loadStatus"
        >
          <ReloadOutlined />
        </a-button>
      </template>
    </a-alert>
    <div class="bind-section">
      <div class="bind-label">{{ t('core.setting.notify.bindStatus') }}</div>
      <div class="bind-row">
        <a-space :size="8">
          <a-spin v-if="binding.statusLoading" size="small" />
          <a-tag v-else-if="binding.status" :color="statusColor">
            {{ statusLabel }}
          </a-tag>
        </a-space>
        <a-space wrap>
          <a-button
            :type="connected ? 'default' : 'primary'"
            :disabled="binding.statusLoading || binding.unbinding || binding.targetSaving"
            @click="binding.start"
          >
            <template #icon><QrcodeOutlined /></template>
            {{ binding.label(connected ? 'Rebind' : 'Bind') }}
          </a-button>
          <a-popconfirm
            v-if="connected"
            v-model:open="unbindConfirmOpen"
            :title="binding.label('UnbindConfirm')"
            :get-popup-container="getContainer"
            @confirm="binding.unbind"
          >
            <a-button danger :loading="binding.unbinding" :disabled="binding.targetSaving">{{
              binding.label('Unbind')
            }}</a-button>
          </a-popconfirm>
        </a-space>
      </div>
    </div>
    <a-form v-if="connected" layout="vertical" class="target-form">
      <a-form-item :label="binding.label('TargetLabel')" html-for="qq-notification-target">
        <div class="target-row">
          <a-select
            id="qq-notification-target"
            :value="binding.groups?.targetType"
            :options="targetOptions"
            :loading="binding.groupsLoading || binding.targetSaving"
            :disabled="
              !binding.groups ||
              binding.groupsLoading ||
              binding.targetSaving ||
              binding.unbinding ||
              binding.open
            "
            :get-popup-container="getContainer"
            class="target-select"
            @change="(value: unknown) => binding.selectTarget(String(value))"
          />
          <a-button
            :loading="binding.groupsLoading"
            :disabled="binding.targetSaving || binding.unbinding || binding.open"
            @click="binding.loadGroups"
          >
            <template #icon><ReloadOutlined /></template>
            {{ binding.label('RefreshGroups') }}
          </a-button>
        </div>
      </a-form-item>
      <QQGroupCommands
        v-if="binding.groups && binding.groups.targetType !== 'c2c'"
        v-model="binding.groupWhitelistDraft"
        :members="binding.groups.groupCommandWhitelist || []"
        :saving="binding.targetSaving"
        :disabled="binding.unbinding || binding.open || binding.targetSaving"
        :save="binding.saveGroupWhitelist"
      />
      <a-alert v-if="binding.groupsError" type="error" show-icon :message="binding.groupsError" />
      <a-typography-paragraph v-if="binding.groups" class="binding-hint">
        {{
          t('core.setting.notify.openclawQqDiscoveredGroups', {
            count: binding.groups.groups?.length || 0,
          })
        }}
      </a-typography-paragraph>
      <a-alert
        v-if="
          binding.groups?.targetType !== 'c2c' && binding.groups && !binding.groups.groups?.length
        "
        type="info"
        show-icon
        :message="binding.label('NoGroupsHint')"
      />
      <a-typography-paragraph type="secondary" class="binding-hint">
        {{ binding.label('GroupHint') }}
      </a-typography-paragraph>
    </a-form>
  </div>
  <a-modal
    :open="binding.open"
    :title="binding.label('LoginTitle')"
    :width="400"
    :z-index="1050"
    :get-container="getContainer"
    :footer="null"
    :body-style="{ maxHeight: 'calc(100vh - 160px)', overflowY: 'auto' }"
    centered
    @cancel="binding.close"
  >
    <div class="qr-content">
      <div class="qr-stage">
        <a-spin v-if="binding.loading || binding.state === 'connecting'" />
        <CheckCircleOutlined v-else-if="binding.state === 'connected'" class="qr-success" />
        <a-button v-else-if="failed" type="primary" @click="binding.start">
          <template #icon><ReloadOutlined /></template>
          {{ binding.label('QrRetry') }}
        </a-button>
        <img
          v-else-if="binding.qrDataUrl"
          :src="binding.qrDataUrl"
          :alt="binding.label('QrAlt')"
          width="240"
          height="240"
        />
      </div>
      <a-alert
        :type="failed ? 'error' : binding.state === 'connected' ? 'success' : 'info'"
        :message="binding.hint"
        show-icon
        role="status"
        class="qr-hint"
      />
      <a-button v-if="binding.state === 'connected'" type="primary" block @click="binding.close">{{
        t('core.common.confirm')
      }}</a-button>
    </div>
  </a-modal>
</template>

<style scoped>
.claw-binding,
.qr-hint {
  width: 100%;
}
.binding-hint {
  margin: 0;
}
.target-form {
  margin-top: 16px;
}
.target-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.target-select {
  flex: 1;
  min-width: 160px;
}
.bind-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bind-label {
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}
.bind-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}
.qr-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}
.qr-stage {
  width: 240px;
  height: 240px;
  display: grid;
  place-items: center;
}
.qr-success {
  font-size: 48px;
  color: var(--ant-color-success);
}
</style>
