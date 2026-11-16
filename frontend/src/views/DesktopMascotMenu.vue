<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type {
  DesktopMascotMenuCapability,
  DesktopMascotMenuData,
  DesktopMascotMenuSize,
} from '@/types/desktopMascot'

const data = ref<DesktopMascotMenuData | null>(null)
const expanded = ref<string | null>(null)
const pending = ref(false)
const error = ref('')
const root = ref<HTMLElement>()
const surface = ref<HTMLElement>()
const viewport = ref<DesktopMascotMenuSize>()
const menuHeight = ref(160)
const feedback = ref<HTMLElement>()
const api = window.desktopMascotMenuAPI
let disposed = false
let unsubscribe: (() => void) | undefined
let observer: ResizeObserver | undefined
let layoutFrame = 0
let lastSize: DesktopMascotMenuSize | undefined
const selected = computed(() => data.value?.capabilities.find(item => item.id === expanded.value))
const entries = computed(
  () =>
    data.value?.presentation.items.map(item => {
      if ('separator' in item) return item
      const capability = data.value?.capabilities.find(
        capability => capability.id === item.capability
      )
      return { ...item, state: capability }
    }) ?? []
)
const style = computed(() => {
  if (!data.value) return {}
  const { colors, presentation } = data.value
  const skin = presentation.style
  return {
    '--mascot-menu-bg': skin?.background ?? colors.background,
    '--mascot-menu-text': skin?.text ?? colors.text,
    '--mascot-menu-border': skin?.border ?? colors.border,
    '--mascot-menu-accent': skin?.accent ?? colors.text,
    '--mascot-menu-radius': `${skin?.radius ?? colors.radius}px`,
    '--mascot-menu-font': `${skin?.fontSize ?? 13}px`,
    '--mascot-menu-item-height': `${skin?.itemHeight ?? 32}px`,
    width: `${Math.min(Math.round(skin?.width ?? 180), viewport.value?.width ?? 180)}px`,
    '--mascot-menu-max-height': `${Math.max(1, Math.min(viewport.value?.height ?? 160, expanded.value ? Math.max(160, menuHeight.value) : Infinity) - 8)}px`,
    '--app-scrollbar-track': 'transparent',
    '--app-scrollbar-thumb': `color-mix(in srgb, ${skin?.text ?? colors.text} 28%, transparent)`,
    '--app-scrollbar-thumb-hover': `color-mix(in srgb, ${skin?.text ?? colors.text} 45%, transparent)`,
  }
})

onMounted(async () => {
  window.addEventListener('keydown', keydown)
  let changed = false
  unsubscribe = api.onChanged(value => {
    changed = true
    data.value = value
  })
  const [initial, available] = await Promise.all([api.getData(), api.getViewport()])
  if (disposed) return
  if (!available) {
    api.close()
    return
  }
  viewport.value = available
  if (!changed) data.value = initial
  await focusFirst()
  measureLayout()
})
watch(root, element => {
  observer?.disconnect()
  if (!element) return
  observer = new ResizeObserver(scheduleLayout)
  observer.observe(element)
})
onUnmounted(() => {
  disposed = true
  unsubscribe?.()
  observer?.disconnect()
  cancelAnimationFrame(layoutFrame)
  window.removeEventListener('keydown', keydown)
})

function scheduleLayout(): void {
  cancelAnimationFrame(layoutFrame)
  layoutFrame = requestAnimationFrame(measureLayout)
}

function measureLayout(): void {
  if (disposed || !viewport.value || !surface.value || !root.value) return
  const bounds = surface.value.getBoundingClientRect()
  const size = { width: Math.ceil(bounds.width), height: Math.ceil(bounds.height) }
  if (!expanded.value) menuHeight.value = size.height
  if (lastSize?.width === size.width && lastSize.height === size.height) return
  lastSize = size
  api.resize(size)
}

async function focusFirst(): Promise<void> {
  await nextTick()
  if (!disposed)
    (root.value?.querySelector<HTMLButtonElement>('button:not(:disabled)') ?? root.value)?.focus()
}

async function choose(capability: DesktopMascotMenuCapability, value?: string): Promise<void> {
  if (pending.value || !capability.enabled) return
  if (capability.options && value === undefined) {
    expanded.value = capability.id
    error.value = ''
    await focusFirst()
    return
  }
  pending.value = true
  error.value = ''
  try {
    const result = await api.execute({
      capability: capability.id,
      ...(value === undefined ? {} : { value }),
    })
    if (disposed) return
    if (result.success) api.close()
    else error.value = result.message || data.value?.unavailableLabel || ''
  } catch {
    if (!disposed) error.value = data.value?.unavailableLabel || ''
  } finally {
    pending.value = false
    await nextTick()
    if (!disposed && error.value) feedback.value?.scrollIntoView({ block: 'nearest' })
  }
}

function back(): void {
  expanded.value = null
  error.value = ''
  void focusFirst()
}

function keydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.preventDefault()
    api.close()
    return
  }
  if (event.key === 'ArrowLeft' && expanded.value) {
    event.preventDefault()
    back()
    return
  }
  if (event.key === 'ArrowRight' && !expanded.value) {
    const button = document.activeElement as HTMLButtonElement | null
    if (button?.getAttribute('aria-haspopup') === 'menu') {
      event.preventDefault()
      button.click()
    }
    return
  }
  const buttons = Array.from(
    root.value?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []
  )
  const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
  if (!buttons.length) return
  if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Tab'].includes(event.key)) {
    event.preventDefault()
    const next =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? buttons.length - 1
          : ((index < 0 && (event.key === 'ArrowUp' || (event.key === 'Tab' && event.shiftKey))
              ? 0
              : index) +
              (event.key === 'ArrowUp' || (event.key === 'Tab' && event.shiftKey) ? -1 : 1) +
              buttons.length) %
            buttons.length
    buttons[next]?.focus()
  }
}
</script>

<template>
  <div
    ref="surface"
    class="menu-surface"
    :style="style"
    @pointerdown.self="api.close()"
    @contextmenu.prevent
  >
    <div v-if="data" ref="root" class="mascot-menu" tabindex="-1" role="menu" :aria-busy="pending">
      <template v-if="selected">
        <div class="menu-heading">
          <button class="menu-back" role="menuitem" @click="back">
            <span aria-hidden="true">‹</span>{{ selected.label }}
          </button>
          <div v-if="!selected.enabled" class="menu-empty" role="status">
            {{ selected.disabledReason ?? data.unavailableLabel }}
          </div>
        </div>
        <div class="menu-options">
          <button
            v-for="option in selected.options"
            :key="option.value"
            role="menuitem"
            :disabled="pending || !selected.enabled || !option.enabled"
            @click="choose(selected, option.value)"
          >
            <span class="menu-label">{{ option.label }}</span>
          </button>
          <div v-if="selected.enabled && !selected.options?.length" class="menu-empty">
            {{ selected.emptyLabel }}
          </div>
        </div>
      </template>
      <div v-else class="menu-items" :class="{ 'menu-grid': data.presentation.layout === 'grid' }">
        <template v-for="(entry, index) in entries" :key="index">
          <div v-if="'separator' in entry" class="menu-separator" role="separator" />
          <button
            v-else
            :role="entry.state?.checked === undefined ? 'menuitem' : 'menuitemcheckbox'"
            :aria-checked="entry.state?.checked"
            :aria-busy="entry.state?.loading"
            :aria-haspopup="entry.state?.options ? 'menu' : undefined"
            :disabled="pending || !entry.state?.enabled"
            :title="
              entry.state?.disabledReason ?? (entry.state ? undefined : data.unavailableLabel)
            "
            @click="entry.state && choose(entry.state)"
          >
            <span v-if="entry.icon" class="menu-icon" aria-hidden="true">{{ entry.icon }}</span>
            <span class="menu-label"
              >{{ entry.state?.label ?? entry.capability }}
              <small v-if="!entry.state?.enabled" class="menu-reason">{{
                entry.state?.disabledReason ?? (entry.state ? undefined : data.unavailableLabel)
              }}</small>
            </span>
            <span v-if="entry.state?.checked" aria-hidden="true">✓</span>
            <span v-if="entry.state?.options" aria-hidden="true">›</span>
          </button>
        </template>
      </div>
      <div v-if="pending" class="menu-progress" role="progressbar" />
      <p v-if="error" ref="feedback" class="menu-error" role="alert">{{ error }}</p>
    </div>
  </div>
</template>

<style scoped>
.menu-surface {
  box-sizing: border-box;
  width: 100%;
  height: auto;
  padding: 4px;
}
.mascot-menu {
  box-sizing: border-box;
  max-height: var(--mascot-menu-max-height);
  overflow: auto;
  padding: 4px;
  color: var(--mascot-menu-text);
  background: var(--mascot-menu-bg);
  border: 1px solid var(--mascot-menu-border);
  border-radius: var(--mascot-menu-radius);
  font:
    var(--mascot-menu-font) / 1.5 system-ui,
    sans-serif;
  user-select: none;
}
.menu-items {
  display: grid;
  gap: 2px;
}
.menu-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
button {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-height: var(--mascot-menu-item-height);
  padding: 4px 8px;
  border: 0;
  border-radius: calc(var(--mascot-menu-radius) / 2);
  color: inherit;
  background: transparent;
  font: inherit;
  text-align: start;
  cursor: pointer;
}
button:hover:not(:disabled),
button:focus-visible {
  background: color-mix(in srgb, var(--mascot-menu-accent) 12%, transparent);
}
button:focus-visible {
  outline: 2px solid var(--mascot-menu-accent);
  outline-offset: -2px;
}
button:disabled {
  cursor: default;
  opacity: 0.45;
}
.menu-label {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.menu-reason {
  display: block;
  font-size: 12px;
}
.menu-icon {
  flex: 0 0 14px;
  text-align: center;
}
.menu-separator {
  grid-column: 1 / -1;
  height: 1px;
  margin: 4px 8px;
  background: var(--mascot-menu-border);
}
.menu-heading {
  position: sticky;
  top: -4px;
  z-index: 1;
  background: var(--mascot-menu-bg);
}
.menu-options {
  display: grid;
  gap: 2px;
}
.menu-empty,
.menu-error {
  margin: 0;
  padding: 8px 10px;
  overflow-wrap: anywhere;
}
.menu-empty {
  opacity: 0.65;
}
.menu-error {
  border-top: 1px solid var(--mascot-menu-border);
}
.menu-progress {
  height: 2px;
  background: var(--mascot-menu-accent);
  opacity: 0.7;
}
</style>
