<script setup lang="ts">
import { computed, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import PluginAvatar from '../components/PluginAvatar.vue'
import PluginOriginTag from '../components/PluginOriginTag.vue'
import MarketInstallStatus from './MarketInstallStatus.vue'
import type { InstallTask } from '../usePluginInstallation'
import {
  actionEditable,
  actionVisible,
  isInstallPhaseActive,
  joinSegments,
  marketAction,
  updateActionLabel,
  type MarketEntryView,
} from '../pluginCenterModel'

/**
 * 市场卡片。描述、标签、状态位缺内容时保留高度，卡片在栅格里等大；
 * 安装按钮出不出现、能不能点由后端界面提示决定，另有插件操作进行中时一律置灰。
 */
const props = defineProps<{ entry: MarketEntryView; task: InstallTask | null; busy: boolean }>()
const emit = defineEmits<{ details: []; install: [] }>()
const { t } = useI18n()
const nameId = useId()

const action = computed(() => marketAction(props.entry))
const installing = computed(() => isInstallPhaseActive(props.task?.phase))
const showButton = computed(
  () => action.value !== 'installed' && !installing.value && actionVisible(props.entry, 'install')
)
const buttonText = computed(() => {
  if (action.value !== 'update') return t('core.plugins.install')
  const label = updateActionLabel(props.entry.version)
  return t(label.key, label.params)
})
const subtitle = computed(() =>
  joinSegments([
    props.entry.version,
    props.entry.updateAvailable && props.entry.installedVersion
      ? t('core.plugins.installedVersion', { version: props.entry.installedVersion })
      : null,
    props.entry.author,
  ])
)
</script>

<template>
  <article class="market-card" :aria-labelledby="nameId">
    <div class="market-card-head">
      <PluginAvatar :icon="entry.icon" />
      <div class="market-card-title">
        <div class="market-card-name-row">
          <strong :id="nameId" class="market-card-name" :title="entry.name">{{
            entry.name
          }}</strong>
          <PluginOriginTag :official="entry.official" />
        </div>
        <div class="market-card-sub" :title="subtitle || undefined">{{ subtitle }}</div>
      </div>
    </div>
    <p class="market-card-description" :title="entry.description ?? undefined">
      {{ entry.description }}
    </p>
    <div class="market-card-tags">
      <a-tag v-for="tag in entry.tags" :key="tag" :bordered="false">{{ tag }}</a-tag>
    </div>
    <MarketInstallStatus :task="task" />
    <div class="market-card-actions">
      <a-button type="link" class="market-card-details" @click="emit('details')">{{
        t('core.plugins.details')
      }}</a-button>
      <span class="market-card-spacer" />
      <a-tag v-if="action === 'installed'" color="success" :bordered="false">{{
        t('core.plugins.alreadyInstalled')
      }}</a-tag>
      <a-button
        v-else-if="showButton"
        type="primary"
        :ghost="action === 'update'"
        :disabled="busy || !actionEditable(entry, 'install')"
        @click="emit('install')"
        >{{ buttonText }}</a-button
      >
    </div>
  </article>
</template>

<style scoped>
.market-card {
  display: flex;
  min-width: 0;
  box-sizing: border-box;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.market-card-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.market-card-title {
  min-width: 0;
  flex: 1;
}

.market-card-name-row {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.market-card-name {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.market-card-sub {
  min-height: 20px;
  overflow: hidden;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.market-card-description {
  display: -webkit-box;
  min-height: 44px;
  margin: 0;
  overflow: hidden;
  line-height: 22px;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

/* 标签只占一行：放不下的整枚折到被裁掉的第二行，不出现半截标签。 */
.market-card-tags {
  display: flex;
  height: 22px;
  flex-wrap: wrap;
  gap: 6px;
  overflow: hidden;
}

.market-card-tags :deep(.ant-tag) {
  max-width: 100%;
  margin-inline-end: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.market-card-actions {
  display: flex;
  min-height: 32px;
  align-items: center;
  gap: 8px;
  margin-top: auto;
}

.market-card-details {
  padding-inline: 0;
}

.market-card-spacer {
  flex: 1;
}

.market-card-actions :deep(.ant-tag) {
  margin-inline-end: 0;
}
</style>
