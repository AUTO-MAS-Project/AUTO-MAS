<template>
  <section class="script-search-bar" role="search" aria-label="搜索脚本">
    <a-input
      ref="inputRef"
      :value="draftValue"
      allow-clear
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

    <span v-if="modelValue" class="script-search-summary" aria-live="polite">{{ summary }}</span>

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
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { CloseOutlined, DownOutlined, SearchOutlined, UpOutlined } from '@ant-design/icons-vue'
import { getScriptSearchEnterDirection } from '@/views/scripts/scriptPageSearch'

interface Props {
  modelValue: string
  summary: string
  matchCount: number
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
/* 行内布局:嵌入工具栏 trailing 槽,与按钮同行向左横向展开,宽度由外层容器控制 */
.script-search-bar {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  flex: 1 1 auto;
  min-width: 0;
  white-space: nowrap;
}

.script-search-input {
  flex: 1 1 auto;
  min-width: 96px;
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

/* 按脚本页容器宽度响应(侧栏挤压时同样生效),不用视口 @media:
   窄容器下仅隐藏摘要的视觉呈现,保留 aria-live 播报 */
@container scripts-page (max-width: 900px) {
  .script-search-summary {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
}
</style>
