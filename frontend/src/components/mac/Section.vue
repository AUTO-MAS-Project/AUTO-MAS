<template>
  <section
    class="mac-section"
    :class="{
      'mac-section--bordered': bordered,
      'mac-section--rounded': rounded,
      'mac-section--collapsible': collapsible,
      'mac-section--collapsed': isCollapsed,
      'mac-section--no-padding': !padding,
    }"
  >
    <header
      v-if="hasHeader"
      :id="headerId"
      class="mac-section__header"
      :role="collapsible ? 'button' : undefined"
      :tabindex="collapsible ? 0 : undefined"
      :aria-expanded="collapsible ? !isCollapsed : undefined"
      :aria-controls="collapsible ? contentId : undefined"
      @click="handleHeaderClick"
      @keydown.enter="toggleCollapse"
      @keydown.space.prevent="toggleCollapse"
    >
      <div class="mac-section__header-content">
        <slot name="header">
          <div class="mac-section__title-group">
            <h2 v-if="title || $slots.title" class="mac-section__title">
              <slot name="title">{{ title }}</slot>
            </h2>
            <p v-if="description" class="mac-section__description">{{ description }}</p>
          </div>
        </slot>
      </div>
      <div
        v-if="$slots.actions"
        class="mac-section__actions"
        @click.stop
        @keydown.stop
        @mousedown.stop
      >
        <slot name="actions" />
      </div>
      <button
        v-if="collapsible"
        type="button"
        class="mac-section__disclosure"
        :aria-label="isCollapsed ? '展开' : '折叠'"
        :aria-controls="contentId"
        tabindex="-1"
        @click.stop
      >
        <svg class="mac-section__chevron" viewBox="0 0 12 12" aria-hidden="true">
          <path
            d="M4.5 2.5L8 6L4.5 9.5"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </header>
    <div
      v-if="title || description || $slots.header || $slots.actions"
      class="mac-section__divider"
      aria-hidden="true"
    />
    <div
      :id="contentId"
      class="mac-section__content-wrapper"
      role="region"
      :aria-labelledby="collapsible ? headerId : undefined"
    >
      <div class="mac-section__content">
        <slot />
      </div>
    </div>
    <footer v-if="$slots.footer" class="mac-section__footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, useSlots, watch } from 'vue'

interface Props {
  title?: string
  description?: string
  collapsible?: boolean
  defaultCollapsed?: boolean
  bordered?: boolean
  rounded?: boolean
  padding?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: undefined,
  description: undefined,
  collapsible: false,
  defaultCollapsed: false,
  bordered: true,
  rounded: true,
  padding: true,
})

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
}>()

const slots = useSlots()
const isCollapsed = ref(props.defaultCollapsed)
const uid = Math.random().toString(36).slice(2, 9)
const contentId = `mac-section-content-${uid}`
const headerId = `mac-section-header-${uid}`

watch(
  () => props.defaultCollapsed,
  val => {
    isCollapsed.value = val
  }
)

const hasHeader = computed(
  () => props.title || props.description || props.collapsible || !!slots.header || !!slots.actions
)

function handleHeaderClick(event: MouseEvent) {
  if (!props.collapsible) return
  const target = event.target as HTMLElement
  if (target.closest('.mac-section__actions') || target.closest('.mac-section__disclosure')) {
    return
  }
  toggleCollapse()
}

function toggleCollapse() {
  if (!props.collapsible) return
  isCollapsed.value = !isCollapsed.value
  emit('update:collapsed', isCollapsed.value)
}
</script>

<style scoped>
.mac-section {
  /* 同一工作台内用半透明磨砂区分层级，避免连续堆叠纯白大块。 */
  background: var(--v6-color-surface-transparent);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  box-shadow: var(--v6-shadow-xs);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
  overflow: hidden;
  transition:
    border-color var(--v6-motion-fast) var(--v6-ease-out),
    box-shadow var(--v6-motion-fast) var(--v6-ease-out),
    border-radius var(--v6-motion-fast) var(--v6-ease-out);
}

.mac-section--bordered {
  border-color: var(--v6-color-border);
}

.mac-section--rounded {
  border-radius: var(--v6-radius-card);
}

.mac-section--collapsed {
  .mac-section__content-wrapper {
    display: grid;
    grid-template-rows: 0fr;
  }

  .mac-section__chevron {
    transform: rotate(0deg);
  }
}

.mac-section--no-padding {
  .mac-section__content {
    padding: 0;
  }
}

.mac-section__header {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  padding: var(--v6-space-3) var(--v6-space-4);
  cursor: default;
  user-select: none;
  transition: background-color var(--v6-motion-fast) var(--v6-ease-out);
}

.mac-section--collapsible .mac-section__header {
  cursor: pointer;
}

.mac-section--collapsible .mac-section__header:hover {
  background: var(--v6-vibrancy-hover);
}

.mac-section__header:focus-visible {
  outline: var(--v6-outline-width) solid var(--v6-color-info);
  outline-offset: calc(-1 * var(--v6-outline-width));
}

.mac-section__header-content {
  flex: 1;
  min-width: 0;
}

.mac-section__title-group {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-0-5);
}

.mac-section__title {
  margin: 0;
  font-size: var(--v6-font-size-base);
  font-weight: var(--v6-font-weight-semibold);
  line-height: var(--v6-line-height-snug);
  color: var(--v6-color-text);
}

.mac-section__description {
  margin: 0;
  font-size: var(--v6-font-size-sm);
  line-height: var(--v6-line-height-normal);
  color: var(--v6-color-text-secondary);
}

.mac-section__actions {
  display: flex;
  align-items: center;
  gap: var(--v6-space-1);
}

.mac-section__disclosure {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  margin: 0;
  background: none;
  border: none;
  border-radius: var(--v6-radius-sm);
  color: var(--v6-color-text-tertiary);
  cursor: pointer;
  flex-shrink: 0;
  transition:
    color var(--v6-motion-fast) var(--v6-ease-out),
    background-color var(--v6-motion-fast) var(--v6-ease-out);
}

.mac-section__disclosure:hover {
  color: var(--v6-color-text);
  background: var(--v6-vibrancy-hover);
}

.mac-section__chevron {
  width: 12px;
  height: 12px;
  transform: rotate(90deg);
  transition: transform var(--v6-motion-base) var(--v6-ease-spring);
}

.mac-section__divider {
  height: 1px;
  background: var(--v6-color-border-subtle);
}

.mac-section__content-wrapper {
  display: grid;
  grid-template-rows: 1fr;
  transition: grid-template-rows var(--v6-motion-base) var(--v6-ease-spring);
}

.mac-section__content {
  padding: var(--v6-space-4);
  overflow: hidden;
}

.mac-section__footer {
  padding: var(--v6-space-3) var(--v6-space-4);
  border-top: 1px solid var(--v6-color-border-subtle);
  background: transparent;
}

:root[data-perf-mode='low'] .mac-section {
  box-shadow: none;
  transition: none;
}

:root[data-perf-mode='low'] .mac-section__header,
:root[data-perf-mode='low'] .mac-section__disclosure,
:root[data-perf-mode='low'] .mac-section__chevron,
:root[data-perf-mode='low'] .mac-section__content-wrapper {
  transition: none;
}

:root[data-perf-mode='low'] .mac-section--collapsed .mac-section__content-wrapper {
  display: none;
}

@media (prefers-reduced-motion: reduce) {
  .mac-section,
  .mac-section__header,
  .mac-section__disclosure,
  .mac-section__chevron,
  .mac-section__content-wrapper {
    transition: none;
  }

  .mac-section--collapsed .mac-section__content-wrapper {
    display: none;
  }
}
</style>
