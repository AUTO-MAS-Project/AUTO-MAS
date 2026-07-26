<template>
  <span
    ref="ringRef"
    class="v6-focus-ring"
    :class="[
      { 'v6-focus-ring--inline': inline },
      { 'v6-focus-ring--inset': inset },
      { 'v6-focus-ring--keyboard': isKeyboardFocus },
      { 'v6-focus-ring--active': isFocused },
    ]"
    :tabindex="tabindex"
    :aria-hidden="ariaHidden"
    @focusin="handleFocusIn"
    @focusout="handleFocusOut"
    @mousedown="handleMouseDown"
    @keydown="handleKeyDown"
  >
    <slot />
  </span>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

interface Props {
  inline?: boolean
  inset?: boolean
  disabled?: boolean
  keyboardOnly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  inline: false,
  inset: false,
  disabled: false,
  keyboardOnly: true,
})

const ringRef = ref<HTMLElement | null>(null)
const isKeyboardFocus = ref(false)
const isFocused = ref(false)

let globalInstanceCount = 0
let globalHadKeyboardEvent = false
let globalKeydownHandler: ((e: KeyboardEvent) => void) | null = null
let globalMousedownHandler: (() => void) | null = null

const tabindex = computed(() => (props.disabled ? '-1' : '-1'))
const ariaHidden = computed(() => props.disabled || undefined)

const ensureGlobalListeners = () => {
  if (globalInstanceCount === 0) {
    globalHadKeyboardEvent = false
    globalKeydownHandler = (e: KeyboardEvent) => {
      if (
        e.key === 'Tab' ||
        e.key === 'ArrowUp' ||
        e.key === 'ArrowDown' ||
        e.key === 'ArrowLeft' ||
        e.key === 'ArrowRight'
      ) {
        globalHadKeyboardEvent = true
      }
    }
    globalMousedownHandler = () => {
      globalHadKeyboardEvent = false
    }
    document.addEventListener('keydown', globalKeydownHandler, true)
    document.addEventListener('mousedown', globalMousedownHandler, true)
  }
  globalInstanceCount++
}

const releaseGlobalListeners = () => {
  globalInstanceCount--
  if (globalInstanceCount === 0) {
    if (globalKeydownHandler) {
      document.removeEventListener('keydown', globalKeydownHandler, true)
      globalKeydownHandler = null
    }
    if (globalMousedownHandler) {
      document.removeEventListener('mousedown', globalMousedownHandler, true)
      globalMousedownHandler = null
    }
    globalHadKeyboardEvent = false
  }
}

const handleKeyDown = (e: KeyboardEvent) => {
  if (props.disabled) return
  if (
    e.key === 'Tab' ||
    e.key === 'ArrowUp' ||
    e.key === 'ArrowDown' ||
    e.key === 'ArrowLeft' ||
    e.key === 'ArrowRight'
  ) {
    globalHadKeyboardEvent = true
  }
}

const handleMouseDown = () => {
  if (props.disabled) return
  globalHadKeyboardEvent = false
  isKeyboardFocus.value = false
}

const handleFocusIn = () => {
  if (props.disabled) return
  isFocused.value = true

  if (props.keyboardOnly) {
    isKeyboardFocus.value = globalHadKeyboardEvent
  } else {
    isKeyboardFocus.value = true
  }
}

const handleFocusOut = () => {
  if (props.disabled) return
  isFocused.value = false
  isKeyboardFocus.value = false
}

onMounted(() => {
  ensureGlobalListeners()
})

onBeforeUnmount(() => {
  releaseGlobalListeners()
})
</script>

<style scoped>
.v6-focus-ring {
  display: block;
  outline: none;
  border-radius: var(--v6-radius-control);
  position: relative;
  transition: box-shadow 0.2s ease;
}

.v6-focus-ring--inline {
  display: inline-block;
}

.v6-focus-ring--inset {
  border-radius: inherit;
}

.v6-focus-ring:focus,
.v6-focus-ring:focus-within {
  outline: none;
}

.v6-focus-ring--keyboard.v6-focus-ring--active:focus,
.v6-focus-ring--keyboard.v6-focus-ring--active:focus-within {
  box-shadow: var(--v6-focus-ring);
}

.v6-focus-ring--inset.v6-focus-ring--keyboard.v6-focus-ring--active:focus,
.v6-focus-ring--inset.v6-focus-ring--keyboard.v6-focus-ring--active:focus-within {
  box-shadow: var(--v6-focus-ring-inset);
}

.v6-focus-ring:not(.v6-focus-ring--keyboard):not(.v6-focus-ring--inset):focus,
.v6-focus-ring:not(.v6-focus-ring--keyboard):not(.v6-focus-ring--inset):focus-within {
  box-shadow: var(--v6-focus-ring);
}

.v6-focus-ring:not(.v6-focus-ring--keyboard).v6-focus-ring--inset:focus,
.v6-focus-ring:not(.v6-focus-ring--keyboard).v6-focus-ring--inset:focus-within {
  box-shadow: var(--v6-focus-ring-inset);
}

/* 低性能模式 / reduced-motion 下保持焦点环可见但去除过渡 */
:root[data-perf-mode='low'] .v6-focus-ring {
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .v6-focus-ring {
    transition: none;
  }
}
</style>
