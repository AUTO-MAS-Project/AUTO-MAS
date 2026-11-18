<template>
  <div
    v-if="entry.missing"
    role="button"
    tabindex="0"
    class="task-row task-row-missing"
    :class="{ 'task-row-selected': selected }"
    @click="emit('select')"
    @keydown.enter="emit('select')"
    @contextmenu="emit('openMenu')"
  >
    <HolderOutlined class="task-drag-handle-disabled" aria-hidden="true" />
    <div class="task-main">
      <span class="task-title task-title-missing">
        {{ title.name }}
        <span v-if="title.index !== null" class="task-copy-index">#{{ title.index }}</span>
      </span>
      <span class="task-missing-tag">{{ t('core.edit.missingTaskTag') }}</span>
    </div>
    <a-popconfirm
      :title="t('core.edit.deleteThisTask2')"
      :ok-text="t('core.edit.ok')"
      :cancel-text="t('core.edit.cancel')"
      :disabled="disabled"
      @confirm="emit('delete')"
    >
      <a-button
        type="text"
        size="small"
        :disabled="disabled"
        :aria-label="t('core.edit.deleteThisTask')"
        @click.stop
      >
        <template #icon>
          <CloseOutlined />
        </template>
      </a-button>
    </a-popconfirm>
  </div>
  <button
    v-else
    type="button"
    class="task-row"
    :class="{ 'task-row-selected': selected, 'task-row-skipped': skipped }"
    @click="emit('select')"
    @contextmenu="emit('openMenu')"
  >
    <HolderOutlined class="task-drag-handle" aria-hidden="true" />
    <img
      v-if="iconUrl"
      :src="iconUrl"
      alt=""
      width="28"
      height="28"
      class="task-icon"
      @error="hideBrokenMaaFWIcon"
      @load="showLoadedMaaFWIcon"
    />
    <div class="task-main">
      <span class="task-title">
        {{ title.name }}
        <span v-if="title.index !== null" class="task-copy-index">#{{ title.index }}</span>
      </span>
      <!-- 只在某几天跑的任务：标题后跟上是哪几天，每天跑的不加 -->
      <span v-if="weekdayNames.length > 0" class="task-weekdays">
        <span v-for="name in weekdayNames" :key="name">{{ name }}</span>
      </span>
      <!-- 多选项勾选数不满足 min_count / max_count：运行器会让整个用户的计划构建失败 -->
      <a-tooltip v-if="optionIssue" :title="t('core.edit.maafwQueueTaskCheckboxCountInvalid')">
        <ExclamationCircleOutlined class="task-option-issue" />
      </a-tooltip>
    </div>
    <span class="task-row-actions" @click.stop>
      <a-tooltip :title="lampLabel">
        <button
          type="button"
          class="task-lamp-button"
          :class="{ 'task-lamp-skipped': skipped }"
          :disabled="disabled"
          :aria-label="lampLabel"
          @click.stop="emit('toggleChecked')"
        >
          <span class="task-lamp" aria-hidden="true" />
        </button>
      </a-tooltip>
      <span class="task-move-stack">
        <button
          type="button"
          :disabled="disabled || !canMoveUp"
          :aria-label="t('core.edit.moveTaskUp')"
          @click.stop="emit('move', -1)"
        >
          <UpOutlined />
        </button>
        <button
          type="button"
          :disabled="disabled || !canMoveDown"
          :aria-label="t('core.edit.moveTaskDown')"
          @click.stop="emit('move', 1)"
        >
          <DownOutlined />
        </button>
      </span>
    </span>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CloseOutlined,
  DownOutlined,
  ExclamationCircleOutlined,
  HolderOutlined,
  UpOutlined,
} from '@ant-design/icons-vue'
import { hideBrokenMaaFWIcon, showLoadedMaaFWIcon } from '../maafwIconImage'
import { maafwQueueEntryTitle } from './maafwTaskSnapshot'
import type { MaaFWQueueEntry } from '@/types/script'

/**
 * 任务队列左栏的一行（普通任务或虚影），拖拽、右键菜单由队列分节统一处理。
 * interface 已没有的任务（项目更新改了 name）是虚影：不能拖、不能移，只能删。
 * 模板根上不能放注释：开发模式下它也算一个节点，vuedraggable 要求每项只有一个根元素。
 */
const props = defineProps<{
  entry: MaaFWQueueEntry
  selected: boolean
  /** 红灯（跳过） */
  skipped: boolean
  disabled: boolean
  canMoveUp: boolean
  canMoveDown: boolean
  /** 多选项勾选数不满足约束 */
  optionIssue: boolean
  /** 只在这几天跑（ISO 星期，1=周一）；每天跑、红灯或不受运行日影响时为 null */
  weekdays: number[] | null
  iconUrl: string
}>()

const emit = defineEmits<{
  select: []
  /** 行上右键：队列分节记下这一行再弹菜单 */
  openMenu: []
  toggleChecked: []
  move: [direction: -1 | 1]
  delete: []
}>()

const { t } = useI18n()

// 星期的简称，周一到周日
const WEEKDAY_SHORT_KEYS = [
  'core.edit.queueTaskWeekdaysShort1',
  'core.edit.queueTaskWeekdaysShort2',
  'core.edit.queueTaskWeekdaysShort3',
  'core.edit.queueTaskWeekdaysShort4',
  'core.edit.queueTaskWeekdaysShort5',
  'core.edit.queueTaskWeekdaysShort6',
  'core.edit.queueTaskWeekdaysShort7',
] as const

const title = computed(() => maafwQueueEntryTitle(props.entry))

const weekdayNames = computed(() =>
  (props.weekdays ?? []).map(day => t(WEEKDAY_SHORT_KEYS[day - 1]))
)

const lampLabel = computed(() => {
  if (props.skipped) return t('core.edit.queueTaskSkipped')
  return t(props.weekdays ? 'core.edit.queueTaskRunsOnWeekdays' : 'core.edit.queueTaskRuns')
})
</script>

<style scoped src="./maafwQueueRow.css"></style>

<style scoped>
.task-row-chosen,
.task-row-drag {
  cursor: grabbing;
}

.task-drag-handle {
  flex: 0 0 auto;
  padding: 4px;
  border-radius: 4px;
  color: var(--ant-color-text-quaternary);
  font-size: 16px;
  cursor: grab;
  transition:
    color 0.15s ease,
    background-color 0.15s ease;
}

.task-drag-handle:hover {
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-tertiary);
}

.task-row-chosen .task-drag-handle,
.task-row-drag .task-drag-handle {
  cursor: grabbing;
}

.task-row-ghost {
  opacity: 0.45;
  background: var(--ant-color-primary-bg);
}

.task-icon {
  width: 28px;
  height: 28px;
  object-fit: contain;
  flex: 0 0 auto;
}

.task-row-skipped .task-icon,
.task-row-skipped .task-title {
  opacity: 0.45;
}

/* 运行日摘要：标题后的一段小字，几天之间留一点空；栏窄时整段换到下一行，英文太长再按天折行 */
.task-weekdays {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0 0.3em;
  margin-left: 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  font-weight: 400;
  vertical-align: baseline;
}

.task-row-actions {
  display: flex;
  align-items: center;
  flex: none;
  gap: 8px;
}

.task-lamp-button {
  --task-lamp-color: var(--ant-color-success);
  width: 24px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  display: grid;
  place-items: center;
  cursor: pointer;
}

.task-lamp {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: radial-gradient(
    circle at 35% 35%,
    color-mix(in srgb, var(--task-lamp-color) 55%, white),
    var(--task-lamp-color) 70%
  );
  box-shadow:
    inset 0 0 0 1px var(--ant-color-border),
    0 0 4px color-mix(in srgb, var(--task-lamp-color) 60%, transparent);
}

.task-lamp-skipped {
  --task-lamp-color: var(--ant-color-error);
}

.task-lamp-skipped .task-lamp {
  box-shadow:
    inset 0 0 0 1px var(--ant-color-border),
    0 0 8px var(--task-lamp-color);
}

.task-move-stack {
  width: 24px;
  height: 32px;
  display: flex;
  flex-direction: column;
  border-radius: 4px;
  overflow: hidden;
}

.task-move-stack button {
  width: 24px;
  height: 16px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--ant-color-text-secondary);
  display: grid;
  place-items: center;
  font-size: 12px;
  cursor: pointer;
}

.task-lamp-button:hover:not(:disabled),
.task-move-stack button:hover:not(:disabled) {
  background: var(--ant-color-fill-tertiary);
}

.task-move-stack button:hover:not(:disabled) {
  color: var(--ant-color-text);
}

.task-lamp-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.task-move-stack button:disabled {
  color: var(--ant-color-text-quaternary);
  cursor: not-allowed;
}

.task-lamp-button:focus-visible,
.task-move-stack button:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}

.task-option-issue {
  margin-left: 6px;
  color: var(--ant-color-warning);
}

/* 同一个任务被加了多份时的副本序号 */
.task-copy-index {
  margin-left: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--ant-color-text-tertiary);
}

/* interface 已没有的任务：置灰、删除线，只留删除 */
.task-row-missing {
  padding-top: 14px;
  padding-bottom: 14px;
  background: var(--ant-color-fill-quaternary);
}

.task-title-missing {
  color: var(--ant-color-text-tertiary);
  font-weight: 400;
  text-decoration: line-through;
}

.task-row-missing .task-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.task-missing-tag {
  flex: none;
  padding: 0 7px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 20px;
  white-space: nowrap;
}

.task-drag-handle-disabled {
  flex: 0 0 auto;
  padding: 4px;
  color: var(--ant-color-text-quaternary);
  font-size: 16px;
  opacity: 0.5;
  cursor: default;
}
</style>
