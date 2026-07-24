<template>
  <section class="script-search-bar" role="search" aria-label="搜索脚本">
    <a-input
      ref="inputRef"
      :value="draftValue"
      allow-clear
      size="large"
      class="script-search-input"
      placeholder="搜索脚本名称、类型、用户、标签或备注"
      @update:value="handleValueUpdate"
      @compositionstart="handleCompositionStart"
      @compositionend="handleCompositionEnd"
      @keydown="handleKeydown"
    >
      <template #prefix>
        <SearchOutlined />
      </template>
    </a-input>

    <span class="script-search-summary" aria-live="polite">{{ summary }}</span>

    <div class="script-search-navigation" aria-label="搜索结果导航">
      <a-tooltip title="上一个匹配项（Shift+Enter）">
        <a-button
          type="text"
          :disabled="matchCount === 0"
          aria-label="上一个匹配项"
          @click="emit('navigate', -1)"
        >
          <template #icon>
            <UpOutlined />
          </template>
        </a-button>
      </a-tooltip>
      <a-tooltip title="下一个匹配项（Enter）">
        <a-button
          type="text"
          :disabled="matchCount === 0"
          aria-label="下一个匹配项"
          @click="emit('navigate', 1)"
        >
          <template #icon>
            <DownOutlined />
          </template>
        </a-button>
      </a-tooltip>
    </div>

    <a-button v-if="modelValue" type="link" @click="emit('clear')">清除</a-button>
    <a-tooltip title="关闭搜索（Esc）">
      <a-button type="text" aria-label="关闭搜索" @click="emit('close')">
        <template #icon>
          <CloseOutlined />
        </template>
      </a-button>
    </a-tooltip>

    <p v-if="dragDisabled" class="script-search-drag-notice">
      <InfoCircleOutlined aria-hidden="true" />
      搜索期间暂停拖拽排序，清除搜索后恢复
    </p>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  CloseOutlined,
  DownOutlined,
  InfoCircleOutlined,
  SearchOutlined,
  UpOutlined,
} from '@ant-design/icons-vue'
import { getScriptSearchEnterDirection } from '@/views/scripts/scriptPageSearch'

interface Props {
  modelValue: string
  summary: string
  matchCount: number
  dragDisabled: boolean
}

interface Emits {
  (event: 'update:modelValue', value: string): void
  (event: 'close'): void
  (event: 'clear'): void
  (event: 'navigate', direction: 1 | -1): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const inputRef = ref<{ focus: () => void } | null>(null)
const draftValue = ref(props.modelValue)
const isComposing = ref(false)

watch(
  () => props.modelValue,
  value => {
    if (!isComposing.value) draftValue.value = value
  }
)

const handleValueUpdate = (value: string) => {
  draftValue.value = value
  if (!isComposing.value) emit('update:modelValue', value)
}

const handleCompositionStart = () => {
  isComposing.value = true
}

const handleCompositionEnd = () => {
  isComposing.value = false
  emit('update:modelValue', draftValue.value)
}

const handleKeydown = (event: KeyboardEvent) => {
  const direction = getScriptSearchEnterDirection(event)
  if (direction === null || props.matchCount === 0) return
  event.preventDefault()
  emit('navigate', direction)
}

const focus = () => inputRef.value?.focus()

defineExpose({ focus })
</script>

<style scoped>
.script-search-bar {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  position: relative;
  margin: calc(var(--v6-space-2) * -1) 0 var(--v6-space-6);
  padding: var(--v6-space-3) var(--v6-space-4);
  background: var(--app-background-panel-bg, var(--v6-color-surface));
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  box-shadow: var(--v6-shadow-card);
}

.script-search-input {
  flex: 1;
  min-width: 240px;
  max-width: 720px;
}

.script-search-summary {
  flex-shrink: 0;
  color: var(--v6-color-text-secondary);
  font-size: 13px;
  white-space: nowrap;
}

.script-search-navigation {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.script-search-drag-notice {
  position: absolute;
  top: calc(100% + var(--v6-space-1));
  left: var(--v6-space-2);
  display: inline-flex;
  align-items: center;
  gap: var(--v6-space-1);
  margin: 0;
  color: var(--v6-color-text-tertiary);
  font-size: 12px;
}

@media (max-width: 900px) {
  .script-search-bar {
    align-items: stretch;
    flex-wrap: wrap;
  }

  .script-search-input {
    max-width: none;
  }

  .script-search-drag-notice {
    position: static;
    flex-basis: 100%;
    padding-left: var(--v6-space-1);
  }
}
</style>
