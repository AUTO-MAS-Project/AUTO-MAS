<template>
  <a-tooltip
    :title="t('plugins.maa_adapter.edit.maaCultivateManageHint')"
    :trigger="['hover', 'focus']"
  >
    <a-button
      class="cultivate-manage-button"
      :type="controller.managed.value ? 'primary' : 'default'"
      :disabled="
        disabled || controller.managing.value || (!sklandBound && !controller.managed.value)
      "
      :loading="controller.managing.value"
      :aria-pressed="controller.managed.value"
      @click="toggle"
    >
      <span class="cultivate-manage-size" aria-hidden="true">{{
        t('plugins.maa_adapter.edit.maaCultivateImportClipboard')
      }}</span>
      <span class="cultivate-manage-label">{{
        t(
          controller.managed.value
            ? 'plugins.maa_adapter.edit.maaCultivateManaged'
            : 'plugins.maa_adapter.edit.maaCultivateUnmanaged'
        )
      }}</span>
    </a-button>
  </a-tooltip>
</template>

<script setup lang="ts">
import { inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { cultivateManagementKey } from './cultivateManagement'

defineProps<{ disabled: boolean; sklandBound: boolean }>()
const { t } = useI18n()
const controller = inject(cultivateManagementKey)
if (!controller) throw new Error('CultivateManageButton requires a cultivation controller')
const toggle = async () => {
  try {
    await controller.setManaged(!controller.managed.value)
  } catch {
    message.error(t('plugins.maa_adapter.edit.maaCultivateManageReloadFailed'))
  }
}
</script>

<style scoped>
.cultivate-manage-button {
  position: relative;
  flex-shrink: 0;
}

/* 与相邻剪贴板按钮使用同一文案占位，三种语言下都保持相同宽度。 */
.cultivate-manage-size {
  visibility: hidden;
}

.cultivate-manage-label {
  position: absolute;
  inset-inline: 0;
  top: 50%;
  transform: translateY(-50%);
}

/* 加载图标不参与文字排版，切换状态时保持按钮与文字位置不变。 */
.cultivate-manage-button :deep(.ant-btn-loading-icon) {
  position: absolute;
  inset-inline-start: 12px;
  top: 50%;
  margin-inline-end: 0;
  transform: translateY(-50%);
}
</style>
