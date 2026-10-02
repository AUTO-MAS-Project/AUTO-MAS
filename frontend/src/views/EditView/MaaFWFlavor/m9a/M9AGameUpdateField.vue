<!-- eslint-disable vue/no-mutating-props -- Slot components edit the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <!-- M9A 的后端特调有游戏客户端更新钩子（官服版本落后时提示或自动下载安装），挂在控制方式分节里与
       游戏包名并排（插入点 besidePackageName） -->
  <a-form-item>
    <template #label>
      <a-tooltip :title="t('edit.m9aFlavorGameUpdateHint')">
        <span class="form-label">
          {{ t('edit.gameUpdate') }}
          <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
        </span>
      </a-tooltip>
    </template>
    <a-select
      v-model:value="context.maafwConfig.Run.GameUpdateMode"
      style="width: 100%"
      :options="gameUpdateModeOptions"
      @change="(value: string | number) => emit('change', 'Run', 'GameUpdateMode', value)"
    />
  </a-form-item>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { MaaFWScriptSlotContext } from '@/composables/maafwFlavorTypes'
import type { MaaFWGameUpdateMode, MaaFWScriptConfig } from '@/types/script'

const { t } = useI18n()

defineProps<{
  context: MaaFWScriptSlotContext
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
}>()

// 三项与后端 MaaFWConfig.Run.GameUpdateMode 的 OptionsValidator 一致
const gameUpdateModeOptions = computed<Array<{ label: string; value: MaaFWGameUpdateMode }>>(() => [
  { label: t('edit.mfwGameUpdateOff'), value: 'Off' },
  { label: t('edit.mfwGameUpdateCheck'), value: 'Check' },
  { label: t('edit.mfwGameUpdateAutoInstall'), value: 'AutoInstall' },
])
</script>

<style scoped>
/* 与控制方式分节里「游戏包名」的标签同一套样式 */
.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}
</style>
