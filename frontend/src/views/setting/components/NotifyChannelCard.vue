<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { NotifyChannelOut } from '@/api/models/NotifyChannelOut'
import { normalizeGroup } from '../notifyChannelView'
import { channelIcon, channelIconColor } from './notifyChannelIcons'

const props = defineProps<{
  channel: NotifyChannelOut
  /** card = 已启用卡片（含自定义 Webhook 卡片）；row = 未启用行 */
  variant: 'card' | 'row'
  /** 状态文案：已启用 / 未启用 / 未绑定 / {n} 条 */
  stateText: string
  /** 状态圆点颜色：绿点或灰点（自定义 Webhook 用灰点） */
  stateActive: boolean
  /** 非敏感摘要；空串时不渲染摘要行 */
  summary: string
}>()

const emit = defineEmits<{ open: [key: string] }>()

const { t } = useI18n()

const icon = computed(() => channelIcon(props.channel.icon))
const iconColor = computed(() => channelIconColor(props.channel.icon))
const groupTag = computed(() =>
  normalizeGroup(props.channel.group) === 'custom'
    ? t('setting.notify.customGroup')
    : t('setting.notify.channelsGroup')
)
const hintText = computed(() =>
  props.channel.customBlock === 'webhook_list'
    ? t('setting.notify.manage')
    : t('setting.notify.configure')
)
</script>

<template>
  <div
    v-if="variant === 'row'"
    class="chan-row"
    role="button"
    tabindex="0"
    @click="emit('open', channel.key)"
    @keydown.enter.prevent="emit('open', channel.key)"
    @keydown.space.prevent="emit('open', channel.key)"
  >
    <span class="chan-icon sm" :style="{ '--c': iconColor, color: iconColor }">
      <component :is="icon" />
    </span>
    <span class="row-name">{{ t(channel.nameKey) }}</span>
    <span class="state idle"><i class="dot off" />{{ stateText }}</span>
  </div>

  <button v-else type="button" class="chan-card" @click="emit('open', channel.key)">
    <div class="chan-card-top">
      <span class="chan-icon" :style="{ '--c': iconColor, color: iconColor }">
        <component :is="icon" />
      </span>
      <span class="state" :class="{ idle: !stateActive }">
        <i class="dot" :class="{ off: !stateActive }" />{{ stateText }}
      </span>
    </div>
    <div class="chan-name">
      {{ t(channel.nameKey) }}<span class="tag">{{ groupTag }}</span>
    </div>
    <div v-if="summary" class="chan-summary" :title="summary">{{ summary }}</div>
    <div class="chan-hint">{{ hintText }} ›</div>
  </button>
</template>

<style scoped>
.chan-card {
  text-align: left;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  padding: 14px 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 116px;
  cursor: pointer;
  color: inherit;
  font: inherit;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease;
}

.chan-card:hover,
.chan-card:focus-visible {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.12);
}

.chan-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.chan-icon {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  font-size: 20px;
  background: color-mix(in srgb, var(--c) 12%, transparent);
}

.chan-icon.sm {
  width: 26px;
  height: 26px;
  flex: 0 0 26px;
  border-radius: 7px;
  font-size: 15px;
}

.state {
  font-size: 12px;
  color: var(--ant-color-success);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.state.idle {
  color: var(--ant-color-text-tertiary);
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ant-color-success);
  display: inline-block;
}

.dot.off {
  background: var(--ant-color-text-tertiary);
  opacity: 0.5;
}

.chan-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.tag {
  font-size: 12px;
  line-height: 18px;
  padding: 0 7px;
  border-radius: 4px;
  background: var(--ant-color-fill-tertiary);
  color: var(--ant-color-text-secondary);
  font-weight: 400;
}

.chan-summary {
  margin-top: auto;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chan-hint {
  font-size: 12px;
  color: var(--ant-color-primary);
  opacity: 0;
  transition: opacity 0.16s ease;
}

.chan-card:hover .chan-hint,
.chan-card:focus-visible .chan-hint {
  opacity: 1;
}

.chan-row {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  padding: 8px 12px;
  min-height: 44px;
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease;
}

.chan-row:hover,
.chan-row:focus-visible {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.12);
}

.row-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  color: var(--ant-color-text);
}
</style>
