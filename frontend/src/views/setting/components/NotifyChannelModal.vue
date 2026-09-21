<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { NotifyChannelOut } from '@/api/models/NotifyChannelOut'
import { handleExternalLink } from '@/utils/openExternal'
import { scopeFields, normalizeGroup } from '../notifyChannelView'
import ClawBinding, { type ClawBindingState } from './ClawBinding.vue'
import NotifyFieldRenderer from './NotifyFieldRenderer.vue'
import WebhookManager from '@/components/WebhookManager.vue'
import { channelIcon, channelIconColor } from './notifyChannelIcons'

const props = withDefaults(
  defineProps<{
    open: boolean
    channel: NotifyChannelOut | null
    /** 取哪组字段；也决定 Webhook 走全局还是用户接口 */
    scope?: 'global' | 'user'
    /** 扁平取值源（settings.Notify / 用户配置的 Notify 组） */
    values: Record<string, unknown>
    /** 保存函数，签名固定 (group, name, value)；用户级宿主自行包一层 */
    save: (group: string, name: string, value: unknown) => unknown
    /** 预留：用户级 Notify.Enabled 总开关会禁用每一个控件 */
    controlsDisabled?: boolean
    /** Claw 渠道的提升绑定状态；非 Claw 渠道传 null */
    clawBinding?: ClawBindingState | null
    /** 嵌套浮层容器；弹窗场景传弹窗 wrap 节点，让浮层整体压在标题栏之下 */
    getPopupContainer?: () => HTMLElement
    scriptId?: string | null
    userId?: string | null
  }>(),
  {
    scope: 'global',
    controlsDisabled: false,
    clawBinding: null,
    getPopupContainer: undefined,
    scriptId: null,
    userId: null,
  }
)

const emit = defineEmits<{
  close: []
  /** Webhook 列表重载后透传条目，供卡片摘要使用 */
  listed: [names: string[]]
}>()

const { t } = useI18n()

const icon = computed(() => channelIcon(props.channel?.icon))
const iconColor = computed(() => channelIconColor(props.channel?.icon))
const groupTag = computed(() =>
  props.channel && normalizeGroup(props.channel.group) === 'custom'
    ? t('setting.notify.customGroup')
    : t('setting.notify.channelsGroup')
)
const fields = computed(() =>
  props.channel ? scopeFields(props.channel, props.scope) : []
)
const enableGroup = computed(() => props.channel?.enableField?.[0] ?? null)
const enableName = computed(() => props.channel?.enableField?.[1] ?? null)
const enabled = computed(() => {
  const name = enableName.value
  return name != null && props.values[name] === true
})
const isClaw = computed(() => (props.channel?.customBlock ?? '').startsWith('claw:'))
const clawConnected = computed(() => !!props.clawBinding?.status?.connected)
// 未绑定时开关不可点（沿用 ClawBinding 原逻辑：未连接 / 查询中 / 解绑中都禁用）
const switchDisabled = computed(() => {
  if (props.controlsDisabled) return true
  if (isClaw.value && props.clawBinding) {
    return !clawConnected.value ||
      props.clawBinding.statusLoading ||
      props.clawBinding.unbinding
  }
  return false
})
const clawChannel = computed(() =>
  props.channel?.customBlock === 'claw:qq' ? 'qq' : 'weixin'
)
const webhookMode = computed(() => (props.scope === 'user' ? 'user' : 'global'))

const saving = ref(false)
const setEnabled = async (value: boolean | string | number) => {
  if (enableGroup.value == null || enableName.value == null) return
  saving.value = true
  try {
    await props.save(enableGroup.value, enableName.value, Boolean(value))
  } finally {
    saving.value = false
  }
}

const saveField = (group: string, name: string, value: unknown) => props.save(group, name, value)

// Webhook 摘要：条目名缺省时用 uid 兜底，避免出现空名字串在列表里
const onWebhookListed = (items: { name: string; uid: string }[]) =>
  emit('listed', items.map(item => item.name || item.uid))
</script>

<template>
  <!-- z-index 900 让弹窗连同遮罩整体压在标题栏（1000）之下；
       内部嵌套浮层挂 wrap 容器后也在这个层叠上下文里 -->
  <!-- transition 名不对应任何 CSS = 瞬显瞬隐；对齐 Scripts.vue 配置MAA 遮罩
       （.maa-config-mask）的无动画行为：长淡入在主线程被内容挂载卡住时会
       掉帧，被感知成遮罩闪一下 -->
  <a-modal
    :open="open"
    :width="480"
    :footer="null"
    :closable="false"
    :z-index="900"
    centered
    wrap-class-name="notify-channel-modal"
    mask-transition-name="notify-mask-fade"
    transition-name="notify-panel-zoom"
    :body-style="{ padding: 0 }"
    @cancel="emit('close')"
  >
    <!-- key 加在内容根节点：换渠道重置弹窗内容，但弹窗本身不重挂 -->
    <div v-if="channel" :key="channel.key" class="modal-inner">
      <div class="modal-head">
        <div class="modal-title-row">
          <span class="chan-icon-head" :style="{ '--c': iconColor, color: iconColor }">
            <component :is="icon" />
          </span>
          <span class="name">{{ t(channel.nameKey) }}</span>
          <span class="tag">{{ groupTag }}</span>
          <a
            v-if="channel.docUrl"
            :href="channel.docUrl"
            class="doc-link"
            @click="handleExternalLink"
          >
            {{ t('common.doc') }}
          </a>
          <button
            type="button"
            class="close"
            :aria-label="t('common.close')"
            @click="emit('close')"
          >
            ✕
          </button>
        </div>
        <div v-if="channel.descKey" class="modal-desc">{{ t(channel.descKey) }}</div>
      </div>

      <div class="modal-body">
        <div v-if="enableName" class="modal-state">
          <div class="state-main">
            <span class="switch-label">{{ t('setting.notify.stateEnabled') }}</span>
            <a-switch
              :checked="enabled && (!isClaw || clawConnected)"
              :loading="saving"
              :disabled="switchDisabled"
              :aria-label="t('setting.notify.stateEnabled')"
              @change="setEnabled"
            />
          </div>
          <div class="state-hint">{{ t('setting.notify.instantHint') }}</div>
        </div>
        <div v-else class="body-hint">{{ t('setting.notify.instantHint') }}</div>

        <ClawBinding
          v-if="isClaw && clawBinding"
          :channel="clawChannel"
          :binding="clawBinding"
          :get-container="getPopupContainer"
        />
        <WebhookManager
          v-else-if="channel.customBlock === 'webhook_list'"
          compact
          :mode="webhookMode"
          :script-id="scriptId"
          :user-id="userId"
          :get-popup-container="getPopupContainer"
          @listed="onWebhookListed"
        />

        <NotifyFieldRenderer
          v-for="field in fields"
          :key="field.name"
          :field="field"
          :value="values[field.name]"
          :disabled="controlsDisabled"
          :get-popup-container="getPopupContainer"
          @save="value => saveField(field.group, field.name, value)"
        />

      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.modal-inner {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.modal-head {
  flex: 0 0 auto;
  padding: 16px 20px 14px;
  border-bottom: 1px solid var(--ant-color-split);
}

.modal-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.chan-icon-head {
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-size: 17px;
  background: color-mix(in srgb, var(--c) 12%, transparent);
}

.modal-title-row .name {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.tag {
  font-size: 12px;
  line-height: 18px;
  padding: 0 7px;
  border-radius: 4px;
  background: var(--ant-color-fill-tertiary);
  color: var(--ant-color-text-secondary);
}

.doc-link {
  margin-left: auto;
  font-size: 13px;
  color: var(--ant-color-primary);
}

.doc-link:hover {
  color: var(--ant-color-primary-hover);
}

.close {
  margin-left: 8px;
  border: none;
  background: transparent;
  color: var(--ant-color-text-tertiary);
  font-size: 15px;
  padding: 2px 6px;
  border-radius: 6px;
  cursor: pointer;
}

.close:hover {
  background: var(--ant-color-fill-tertiary);
  color: var(--ant-color-text);
}

.modal-desc {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--ant-color-text-tertiary);
}

/* 恰好一个滚动者：低窗口高度下内容在弹窗体内滚动，页面与弹窗壳都不滚 */
.modal-body {
  overflow-y: auto;
  max-height: calc(100vh - 240px);
  padding: 16px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-state {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 8px 14px;
}

.state-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.switch-label {
  font-size: 14px;
  color: var(--ant-color-text);
}

.state-hint,
.body-hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>

