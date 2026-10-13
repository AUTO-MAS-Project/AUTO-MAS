<template>
  <a-modal
    :open="open"
    :title="t('edit.taskTimeLimitOverrides')"
    :width="560"
    destroy-on-close
    @cancel="emit('update:open', false)"
  >
    <div class="task-limit-modal">
      <div class="task-limit-row loop-guard-row">
        <span class="task-limit-label">{{ t('edit.loopGuard') }}</span>
        <a-switch v-model:checked="loopGuardDraft" />
      </div>
      <div class="task-limit-modal-sub">{{ t('edit.taskTimeLimitModalSub') }}</div>
      <!-- 列表定高、内部滚动：任务多的项目也不会把弹窗撑出屏幕 -->
      <div class="task-limit-modal-list">
        <div
          v-for="task in tasks"
          :key="task.value"
          class="task-limit-row"
          :class="{ 'is-changed': isChanged(task.value) }"
        >
          <span class="task-limit-label" :title="task.label">{{ task.label }}</span>
          <span v-if="isChanged(task.value)" class="task-limit-hint">
            {{ defaultText }}
            <a class="task-limit-link" @click="draft[task.value] = null">
              {{ t('edit.taskTimeLimitRestore') }}
            </a>
          </span>
          <a-input-number
            :value="draft[task.value] ?? null"
            :min="0"
            :max="9999"
            :precision="0"
            :placeholder="String(defaultMinutes)"
            class="task-limit-input"
            @update:value="(value: number | string | null) => setMinutes(task.value, value)"
          />
        </div>
      </div>
    </div>
    <template #footer>
      <div class="task-limit-footer">
        <a-button
          type="link"
          class="task-limit-reset-all"
          :disabled="!anyChanged"
          @click="resetAll"
        >
          {{ t('edit.taskTimeLimitRestoreAll') }}
        </a-button>
        <a-space>
          <a-button @click="emit('update:open', false)">{{ t('common.cancel') }}</a-button>
          <a-button type="primary" @click="handleSave">
            {{ t('edit.taskTimeLimitSave') }}
          </a-button>
        </a-space>
      </div>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  taskLimitDraftToOverrides,
  type TaskTimeLimitDraft,
  type TaskTimeLimitOverrides,
} from './taskTimeLimits'

const props = defineProps<{
  open: boolean
  /** interface 的全部任务（去掉 pretask 伪任务），按 interface 顺序 */
  tasks: Array<{ label: string; value: string }>
  /** 打开时已存的单独设置（任务名 → 分钟） */
  values: TaskTimeLimitOverrides
  /** 打开时已存的原地打转检测开关（Run.LoopGuard） */
  loopGuard: boolean
  /** 全局默认的单任务时限（分钟），0 表示不限 */
  defaultMinutes: number
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  /** 点了保存：交回全部单独设置（留空的行不在里面）与原地打转检测开关 */
  save: [values: TaskTimeLimitOverrides, loopGuard: boolean]
}>()

const { t } = useI18n()

/** 弹窗内的草稿：取消即丢弃 */
const draft = reactive<TaskTimeLimitDraft>({})
const loopGuardDraft = ref(false)

const resetDraft = () => {
  for (const key of Object.keys(draft)) delete draft[key]
  for (const task of props.tasks) {
    draft[task.value] = props.values[task.value] ?? null
  }
  loopGuardDraft.value = props.loopGuard
}

watch(
  () => props.open,
  value => {
    if (value) resetDraft()
  },
  { immediate: true }
)

const defaultText = computed(() =>
  props.defaultMinutes > 0
    ? t('edit.taskTimeLimitDefault', { n: props.defaultMinutes })
    : t('edit.taskTimeLimitDefaultUnlimited')
)

// 留空 = 跟随默认；填了数字（含 0 = 不限、含等于默认值）就算单独设置
const isChanged = (name: string) => typeof draft[name] === 'number'

const anyChanged = computed(() => props.tasks.some(task => isChanged(task.value)))

const setMinutes = (name: string, value: number | string | null) => {
  draft[name] = value === null || value === '' ? null : Number(value)
}

const resetAll = () => {
  for (const task of props.tasks) draft[task.value] = null
}

const handleSave = () => {
  emit('save', taskLimitDraftToOverrides(draft), loopGuardDraft.value)
  emit('update:open', false)
}
</script>

<style scoped>
.loop-guard-row {
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.task-limit-modal-sub {
  padding: 0 0 8px;
  color: var(--ant-color-text-secondary);
}

.task-limit-modal-list {
  height: 440px;
  max-height: calc(100vh - 340px);
  margin-right: -12px;
  padding-right: 12px;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.task-limit-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
}

.task-limit-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--ant-color-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-limit-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  white-space: nowrap;
}

.task-limit-link {
  color: var(--ant-color-primary);
}

.task-limit-input {
  width: 120px;
}

.task-limit-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
}

.task-limit-reset-all {
  padding: 0;
}
</style>
