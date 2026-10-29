<template>
  <!-- 队列为空：先列我的模板，再列项目预设，哪组没有就不显示那组 -->
  <div class="preset-section">
    <template v-if="queueTemplates.length > 0">
      <div class="preset-group-title">{{ t('core.edit.queueTemplateMine') }}</div>
      <MaaFWQueueCard
        v-for="template in queueTemplates"
        :key="template.name"
        kind="template"
        :title="template.name"
        :task-count="template.chips.length"
        :invalid-count="template.invalidCount"
        :chips="template.chips"
      >
        <template #actions>
          <a-button
            type="primary"
            :disabled="template.entries.length === 0"
            @click="emit('applyQueueTemplate', template.name)"
          >
            {{ t('core.edit.queueTemplateApply') }}
          </a-button>
        </template>
      </MaaFWQueueCard>
    </template>
    <template v-if="presetTemplates.length > 0">
      <div class="preset-group-title">{{ t('core.edit.queueTemplatePresets') }}</div>
      <!-- 列出来的预设都能应用（只有前置任务设置的也算），按钮不置灰 -->
      <MaaFWQueueCard
        v-for="template in presetTemplates"
        :key="template.preset.name"
        kind="preset"
        :title="template.preset.label || template.preset.name"
        :description="template.preset.description"
        :base-path="basePath"
        :chips="presetTemplateChips(template)"
      >
        <template #actions>
          <a-button type="primary" @click="emit('applyPresetTemplate', template.preset.name)">
            {{ t('core.edit.applyPreset2') }}
          </a-button>
        </template>
      </MaaFWQueueCard>
    </template>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { presetTemplateChips } from '../maafwPresetQueue'
import type { MaaFWQueueTemplateView, PresetTemplate } from '../../MaaFWFlavor/sectionContracts'
import MaaFWQueueCard from './MaaFWQueueCard.vue'

/**
 * 队列为空时队列框里的入口：我的模板与项目预设两组卡片，点「应用」交回页面替换队列。
 * 只管显示与交回动作。
 */

defineProps<{
  queueTemplates: MaaFWQueueTemplateView[]
  presetTemplates: PresetTemplate[]
  /** 预设描述里的图片按项目目录解析 */
  basePath: string
}>()

const emit = defineEmits<{
  applyQueueTemplate: [name: string]
  applyPresetTemplate: [presetName: string]
}>()

const { t } = useI18n()
</script>

<style scoped>
.preset-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
}

/* 分组小标题：我的模板 / 项目预设 */
.preset-group-title {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  font-weight: 600;
}
</style>
