<script setup lang="ts">
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import SettingRow from '@/components/ui/SettingRow.vue'
import { CURSOR_SIZE_MAX, CURSOR_SIZE_MIN } from '@/components/appearanceCursor'
import { useTheme } from '@/composables/useTheme'

const { t } = useI18n()
const { cursorSizePx, previewCursorSize } = useTheme()

function changeSize(value: number | string | null) {
  if (typeof value === 'string') return
  previewCursorSize(value, () => message.error(t('core.setting.basic.cursorSizeSaveFailed')))
}
</script>

<template>
  <SettingRow
    :label="t('core.setting.basic.cursorSize')"
    :hint="t('core.setting.basic.cursorSizeHint')"
  >
    <div class="cursor-size-controls">
      <a-slider
        class="cursor-size-slider"
        :value="cursorSizePx ?? CURSOR_SIZE_MIN"
        :min="CURSOR_SIZE_MIN"
        :max="CURSOR_SIZE_MAX"
        :step="1"
        :aria-label="t('core.setting.basic.cursorSize')"
        @update:value="changeSize"
      />
      <a-input-number
        :value="cursorSizePx"
        :min="CURSOR_SIZE_MIN"
        :max="CURSOR_SIZE_MAX"
        :precision="0"
        :step="1"
        :aria-label="t('core.setting.basic.cursorSize')"
        placeholder="—"
        @update:value="(value: number | string | null) => value !== null && changeSize(value)"
      />
      <span>px</span>
      <a-button :disabled="cursorSizePx === null" @click="changeSize(null)">
        {{ t('core.setting.basic.cursorSizeReset') }}
      </a-button>
    </div>
  </SettingRow>
</template>

<style scoped>
.cursor-size-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.cursor-size-slider {
  width: 120px;
}
html.appearance-cursor-custom .cursor-size-slider {
  cursor: var(--app-appearance-cursor-pointer);
}
</style>
