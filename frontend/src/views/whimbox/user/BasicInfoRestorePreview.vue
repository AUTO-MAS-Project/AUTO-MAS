<template>
  <NoData v-if="!sections.length" :description="t('core.edit.configRestorePreviewEmpty')" />
  <template v-else>
    <template v-for="section in sections" :key="section.name">
      <h4 class="whimbox-preview-section">{{ section.label }}</h4>
      <a-descriptions :column="1" size="small" bordered class="whimbox-preview-box">
        <a-descriptions-item v-for="row in section.rows" :key="row.key" :label="row.key">
          {{ row.value }}
        </a-descriptions-item>
      </a-descriptions>
    </template>
  </template>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ raw: unknown }>()
const { t } = useI18n()

// 预览响应原文收敛为分区视图（两池同构：sections[].rows[]；文件清单由基座渲染）
interface WhimboxPreviewSection {
  name: string
  label: string
  rows: Array<{ key: string; value: string }>
}
const sections = computed((): WhimboxPreviewSection[] => {
  const raw = props.raw
  if (!raw || typeof raw !== 'object') return []
  const sections = (raw as { sections?: unknown }).sections
  if (!Array.isArray(sections)) return []
  return sections
    .filter((s): s is Record<string, unknown> => Boolean(s && typeof s === 'object'))
    .map(s => ({
      name: String(s.name ?? ''),
      label: String(s.label ?? ''),
      rows: Array.isArray(s.rows)
        ? s.rows
            .filter((r): r is Record<string, unknown> => Boolean(r && typeof r === 'object'))
            .map(r => ({ key: String(r.key ?? ''), value: String(r.value ?? '') }))
        : [],
    }))
    .filter(s => s.rows.length > 0)
})
</script>

<style scoped>
.whimbox-preview-box {
  margin-top: 8px;
}

.whimbox-preview-section {
  margin: 12px 0 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.whimbox-preview-section:first-child {
  margin-top: 0;
}
</style>
