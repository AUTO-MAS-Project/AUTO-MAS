<template>
  <div class="mirror-panel">
    <p class="mirrors-title">{{ title || t('init.failure.mirrorTitle') }}</p>
    <button
      v-for="mirror in mirrors"
      :key="mirror.key"
      type="button"
      class="mirror-option"
      :class="{ selected: selectedMirror === mirror.key }"
      role="radio"
      :aria-checked="selectedMirror === mirror.key"
      @click="emit('update:selected-mirror', mirror.key)"
    >
      <span class="mirror-radio" aria-hidden="true"></span>
      <span class="mirror-name">{{ mirror.name }}</span>
      <span class="mirror-note">
        {{ mirror.recommended ? t('init.failure.mirrorRecommended') : mirror.description }}
      </span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { MirrorConfig } from '@/types/mirror'

defineOptions({ name: 'MirrorSelectPanel' })

interface Props {
  mirrors?: MirrorConfig[]
  selectedMirror?: string
  /** 面板标题，默认复用失败态的「选择镜像源」。 */
  title?: string
}

withDefaults(defineProps<Props>(), {
  mirrors: () => [],
  selectedMirror: '',
  title: '',
})

const emit = defineEmits<{
  'update:selected-mirror': [value: string]
}>()

const { t } = useI18n()
</script>

<style scoped>
.mirror-panel {
  margin-top: 18px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  overflow: hidden;
}

.mirrors-title {
  margin: 0;
  padding: 9px 14px;
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.mirror-option {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 10px;
  padding: 9px 14px;
  border: 0;
  border-top: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.mirror-option:hover {
  background: var(--ant-color-fill-quaternary);
}

.mirror-radio {
  flex: none;
  width: 13px;
  height: 13px;
  border: 1px solid var(--ant-color-border);
  border-radius: 50%;
}

.mirror-option.selected .mirror-radio {
  border: 4px solid var(--ant-color-primary);
}

.mirror-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mirror-note {
  margin-left: auto;
  padding-left: 12px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  white-space: nowrap;
}
</style>
