<template>
  <div
    ref="boxRef"
    class="hotkey-input"
    :class="{ 'is-recording': recording, 'is-error': error, 'is-changed': changed }"
    tabindex="0"
    role="button"
    :aria-label="ariaLabel"
    @mousedown.prevent="toggleRecording"
    @keydown="handleKeydown"
    @blur="setRecording(false)"
  >
    <span v-if="recording" class="hotkey-placeholder">{{ t('edit.mfwHotkeyPressKeys') }}</span>
    <template v-else>
      <template v-for="(key, index) in keys" :key="index">
        <span v-if="index > 0" class="hotkey-plus">+</span>
        <span class="hotkey-cap">{{ displayKey(key) }}</span>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  displayKey,
  hotkeyFromKeyboardEvent,
  parseHotkey,
  type HotkeyEventResult,
} from '@/utils/maafwHotkey'

const props = defineProps<{
  /** 当前组合键（存储串） */
  value: string
  /** 与默认不同：键帽转主色 */
  changed?: boolean
  /** 上次录制失败：红框（错误文字由所在行显示） */
  error?: boolean
  /** 读屏用的字段名 */
  label?: string
}>()

const emit = defineEmits<{
  /** 录到了一次结果（组合键或错误），录制随之结束 */
  record: [result: Exclude<HotkeyEventResult, { kind: 'ignored' } | { kind: 'modifier-only' }>]
  /** 录制状态变化：弹窗据此在录制中屏蔽 Esc 关闭 */
  recording: [value: boolean]
}>()

const { t } = useI18n()

const boxRef = ref<HTMLDivElement>()
const recording = ref(false)

const keys = computed(() => parseHotkey(props.value))
const ariaLabel = computed(() =>
  [props.label, keys.value.map(displayKey).join(' + ')].filter(Boolean).join(': ')
)

const setRecording = (value: boolean) => {
  if (recording.value === value) return
  recording.value = value
  emit('recording', value)
}

// mousedown 阻止了默认聚焦，自己把焦点放上来，失焦才能取消录制
const toggleRecording = () => {
  boxRef.value?.focus({ preventScroll: true })
  setRecording(!recording.value)
}

const handleKeydown = (event: KeyboardEvent) => {
  if (!recording.value) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      setRecording(true)
    }
    return
  }
  // 录制中所有按键都归录制框：不滚动、不切焦点，也不让弹窗收到 Esc
  event.preventDefault()
  event.stopPropagation()
  const result = hotkeyFromKeyboardEvent(event)
  // 单按修饰键不结束录制；没有键信息的合成事件忽略
  if (result.kind === 'ignored' || result.kind === 'modifier-only') return
  setRecording(false)
  emit('record', result)
}
</script>

<style scoped>
.hotkey-input {
  display: flex;
  flex: none;
  align-items: center;
  gap: 4px;
  width: 168px;
  height: 32px;
  padding: 0 7px;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  background: var(--ant-color-bg-container);
  cursor: pointer;
  outline: none;
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
}

.hotkey-input:hover,
.hotkey-input:focus-visible {
  border-color: var(--ant-color-primary);
}

.hotkey-input.is-recording {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg);
}

.hotkey-input.is-error {
  border-color: var(--ant-color-error);
}

.hotkey-placeholder {
  color: var(--ant-color-text-tertiary);
  white-space: nowrap;
}

.hotkey-plus {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.hotkey-cap {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 7px;
  border: 1px solid var(--ant-color-border);
  border-bottom-width: 2px;
  border-radius: 4px;
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-text);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.is-changed .hotkey-cap {
  border-color: var(--ant-color-primary-border);
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
}
</style>
