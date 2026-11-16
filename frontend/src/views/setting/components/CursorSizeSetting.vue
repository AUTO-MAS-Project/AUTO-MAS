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
    stacked
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
      <div class="cursor-size-value">
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
      </div>
      <a-button :disabled="cursorSizePx === null" @click="changeSize(null)">
        {{ t('core.setting.basic.cursorSizeReset') }}
      </a-button>
    </div>
  </SettingRow>
</template>

<style scoped>
.cursor-size-controls {
  display: grid;
  grid-template-columns: minmax(80px, 1fr) auto auto;
  width: 100%;
  align-items: center;
  gap: 8px;
}

.cursor-size-slider {
  min-width: 0;
  margin-inline: 6px;
}
.cursor-size-value {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.cursor-size-value :deep(.ant-input-number) {
  width: 72px;
}
.cursor-size-controls > .ant-btn {
  justify-self: end;
}
/* 小卡片先让滑条独占一行，数值、单位与恢复按钮仍保持同行。 */
@container (max-width: 320px) {
  .cursor-size-controls {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .cursor-size-slider {
    grid-column: 1 / -1;
  }
}

html.appearance-cursor-custom .cursor-size-slider {
  cursor: var(--app-appearance-cursor-pointer);
}
</style>
