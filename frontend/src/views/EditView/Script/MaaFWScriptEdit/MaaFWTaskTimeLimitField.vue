<template>
  <a-form-item>
    <template #label>
      <span class="form-label">{{ t('edit.taskTimeLimitOverrides') }}</span>
    </template>
    <a-input-group compact class="path-input-group">
      <a-input :value="summary" size="large" class="path-input" readonly />
      <a-button size="large" class="path-button" :disabled="disabled" @click="modalOpen = true">
        <template #icon>
          <SettingOutlined />
        </template>
        {{ t('edit.taskTimeLimitSet') }}
      </a-button>
    </a-input-group>
  </a-form-item>
  <MaaFWTaskTimeLimitModal
    v-model:open="modalOpen"
    :tasks="tasks"
    :values="storedOverrides"
    :loop-guard="loopGuard"
    :default-minutes="defaultMinutes"
    @save="handleSave"
  />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { SettingOutlined } from '@ant-design/icons-vue'
import MaaFWTaskTimeLimitModal from './MaaFWTaskTimeLimitModal.vue'
import {
  countTaskLimitOverrides,
  parseTaskLimitOverrides,
  stringifyTaskLimitOverrides,
  type TaskTimeLimitOverrides,
} from './taskTimeLimits'

const props = defineProps<{
  /** 脚本配置 Run.TaskTimeLimitOverrides（JSON 字符串） */
  value: string | Record<string, number> | undefined
  /** 脚本配置 Run.LoopGuard（原地打转检测，开关在弹窗里） */
  loopGuard: boolean
  /** interface 的全部任务（与周期跳过下拉同一份选项） */
  tasks: Array<{ label: string; value: string }>
  /** 全局默认的单任务时限（分钟） */
  defaultMinutes: number
  /** interface 没读到或没有任务时不能设置 */
  disabled: boolean
}>()

const emit = defineEmits<{
  /** 保存后的 Run.TaskTimeLimitOverrides（JSON 字符串）与 Run.LoopGuard */
  save: [value: string, loopGuard: boolean]
}>()

const { t } = useI18n()

const modalOpen = ref(false)

const storedOverrides = computed(() => parseTaskLimitOverrides(props.value))

const summary = computed(() => {
  const count = countTaskLimitOverrides(storedOverrides.value)
  return count > 0
    ? t('edit.taskTimeLimitChanged', { n: count })
    : t('edit.taskTimeLimitAllDefault')
})

const handleSave = (values: TaskTimeLimitOverrides, loopGuard: boolean) => {
  emit('save', stringifyTaskLimitOverrides(values), loopGuard)
}
</script>

<style scoped>
/* 与键位映射那组同一套样式（scoped 样式不跨组件，照抄一份） */
.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
}

.path-input:focus {
  box-shadow: none !important;
}

.path-button {
  border: none;
  border-left: 1px solid var(--ant-color-border-secondary);
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
}

/* interface 没读到时按钮禁用：不能还是主色（antd 的 colorBgContainerDisabled 就是 fill-tertiary） */
.path-button:disabled,
.path-button.ant-btn-disabled {
  color: var(--ant-color-text-disabled);
  background: var(--ant-color-fill-tertiary);
  cursor: not-allowed;
}
</style>
