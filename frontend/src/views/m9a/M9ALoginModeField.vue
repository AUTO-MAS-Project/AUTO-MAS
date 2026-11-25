<!-- eslint-disable vue/no-mutating-props -- Slot components edit the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <!-- M9A 的后端特调可让 MAS 完成 B 服登录（隐私政策提示 + 登录记录选号），登录回到标题页后再交给
       M9A 的启动任务进游戏；挂在控制方式分节里，排在游戏包名、等待时间之后，单独一格（M9A 专属脚本页经
       control 分节的 besidePackageName 格放进来） -->
  <a-form-item>
    <template #label>
      <a-tooltip :title="t('core.edit.m9aFlavorLoginModeHint')">
        <span class="form-label">
          {{ t('core.edit.m9aFlavorLoginMode') }}
          <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
        </span>
      </a-tooltip>
    </template>
    <a-select
      v-model:value="maafwConfig.Run.LoginMode"
      style="width: 100%"
      :options="loginModeOptions"
      @change="(value: string | number) => emit('change', 'Run', 'LoginMode', value)"
    />
  </a-form-item>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { MaaFWLoginMode, MaaFWScriptConfig } from '@/types/script'

const { t } = useI18n()

defineProps<{
  maafwConfig: MaaFWScriptConfig
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
}>()

// 两项与后端 M9AConfig.Run.LoginMode 一致
const loginModeOptions = computed<Array<{ label: string; value: MaaFWLoginMode }>>(() => [
  { label: t('core.edit.m9aLoginModeProject'), value: 'Project' },
  { label: t('core.edit.m9aLoginModeMas'), value: 'Mas' },
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
