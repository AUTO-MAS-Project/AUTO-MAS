<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { AppModal } from '@/components/ui'
import PluginReleaseNotes from '../components/PluginReleaseNotes.vue'
import PluginAvatar from '../components/PluginAvatar.vue'
import PluginDetailFields from '../components/PluginDetailFields.vue'
import PluginOriginTag from '../components/PluginOriginTag.vue'
import { joinSegments, type MarketEntryView } from '../pluginCenterModel'

/** 市场条目详情：图标、名称、官方标识、描述、字段与三类链接；缺哪项不显示哪项。 */
const props = defineProps<{ entry: MarketEntryView | null }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()

/** 宽 560 时字段排成两列。 */
const FIELD_COLUMN_MIN_WIDTH = 200

const subtitle = computed(() =>
  props.entry
    ? joinSegments([
        props.entry.version,
        // 和卡片一致：只在可更新时才提已装版本，否则两个版本号相同、重复。
        props.entry.updateAvailable && props.entry.installedVersion
          ? t('core.plugins.installedVersion', { version: props.entry.installedVersion })
          : null,
      ])
    : ''
)
</script>

<template>
  <AppModal :open="entry !== null" :width="560" footer="close" @cancel="emit('close')">
    <template #header>
      <div v-if="entry" class="market-detail-head">
        <PluginAvatar :icon="entry.icon" />
        <div class="market-detail-title">
          <div class="market-detail-name-row">
            <span class="market-detail-name">{{ entry.name }}</span>
            <PluginOriginTag :official="entry.official" />
          </div>
          <div v-if="subtitle" class="market-detail-sub">{{ subtitle }}</div>
        </div>
      </div>
    </template>
    <PluginDetailFields v-if="entry" :view="entry" :min-column-width="FIELD_COLUMN_MIN_WIDTH" />
    <PluginReleaseNotes
      v-if="entry"
      :key="entry.uid"
      :notes="entry.updateAvailable ? entry.updateNotes : entry.releaseNotes"
      :upgrade="entry.updateAvailable"
    />
  </AppModal>
</template>

<style scoped>
.market-detail-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-inline-end: 24px;
}

.market-detail-title {
  min-width: 0;
  flex: 1;
}

.market-detail-name-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.market-detail-name {
  overflow-wrap: anywhere;
}

.market-detail-sub {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: normal;
  line-height: 20px;
}
</style>
