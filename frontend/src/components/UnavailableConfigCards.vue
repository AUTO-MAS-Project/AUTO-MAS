<script setup lang="ts">
import { DeleteOutlined } from '@ant-design/icons-vue'
import { Modal } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'

/** 所属插件不可用的托管或计划表：只读，只能删除。 */
export interface UnavailableConfigCard {
  uid: string
  name: string
  typeLabel: string
  /** plugin_disabled：插件在但没启用（列表里 pluginAvailable 为 false 的条目） */
  reason: 'plugin_unavailable' | 'load_failed' | 'plugin_disabled'
  plugin?: string | null
  detail?: string | null
}

const props = defineProps<{
  items: readonly UnavailableConfigCard[]
  kind: 'script' | 'plan'
  deletingId?: string | null
}>()
const emit = defineEmits<{ delete: [uid: string] }>()

const { t } = useI18n()

const reasonText = (item: UnavailableConfigCard) => {
  const plugin = item.plugin || t('core.unavailableConfig.unknownPlugin')
  if (item.reason === 'load_failed') return t('core.unavailableConfig.loadFailed', { plugin })
  if (item.reason === 'plugin_disabled') return t('core.unavailableConfig.pluginDisabled')
  return t('core.unavailableConfig.pluginUnavailable', { plugin })
}

const confirmDelete = (item: UnavailableConfigCard) => {
  Modal.confirm({
    title: t(
      props.kind === 'plan'
        ? 'core.unavailableConfig.deletePlanTitle'
        : 'core.unavailableConfig.deleteScriptTitle',
      { name: item.name || item.uid }
    ),
    content: t('core.unavailableConfig.deleteContent'),
    okText: t('core.unavailableConfig.delete'),
    okType: 'danger',
    cancelText: t('core.common.cancel'),
    onOk: () => emit('delete', item.uid),
  })
}
</script>

<template>
  <div v-if="items.length" class="unavailable-configs">
    <div v-for="item in items" :key="item.uid" class="unavailable-card">
      <div class="unavailable-main">
        <div class="unavailable-title">
          <span class="unavailable-name">{{ item.name || item.uid }}</span>
          <a-tag>{{ item.typeLabel }}</a-tag>
        </div>
        <div class="unavailable-reason">{{ reasonText(item) }}</div>
        <div v-if="item.detail" class="unavailable-detail">{{ item.detail }}</div>
      </div>
      <a-button danger :loading="deletingId === item.uid" @click="confirmDelete(item)">
        <template #icon><DeleteOutlined /></template>
        {{ t('core.unavailableConfig.delete') }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.unavailable-configs {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.unavailable-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 12px;
  background: var(--ant-color-fill-quaternary);
}

.unavailable-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.unavailable-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.unavailable-name {
  overflow-wrap: anywhere;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
}

.unavailable-reason {
  color: var(--ant-color-warning-text);
  font-size: 13px;
}

.unavailable-detail {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  overflow-wrap: anywhere;
}
</style>
