<template>
  <div
    class="mac-toolbar"
    :class="[
      `mac-toolbar--${position}`,
      {
        'mac-toolbar--compact': compact,
        'mac-toolbar--bordered': bordered,
        'mac-toolbar--transparent': transparent,
      },
    ]"
    role="toolbar"
    :aria-label="ariaLabel"
  >
    <div v-if="$slots.leading" class="mac-toolbar__leading">
      <slot name="leading" />
    </div>
    <div class="mac-toolbar__center">
      <slot />
    </div>
    <div v-if="$slots.trailing" class="mac-toolbar__trailing">
      <slot name="trailing" />
    </div>
    <div v-if="$slots.divider && position !== 'none'" class="mac-toolbar__custom-divider">
      <slot name="divider" />
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  compact?: boolean
  bordered?: boolean
  position?: 'top' | 'bottom' | 'both' | 'none'
  transparent?: boolean
  ariaLabel?: string
}

withDefaults(defineProps<Props>(), {
  compact: false,
  bordered: true,
  position: 'bottom',
  transparent: false,
  ariaLabel: '工具栏',
})
</script>

<style scoped>
.mac-toolbar {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  padding: var(--v6-space-2) var(--v6-space-4);
  background: var(--v6-vibrancy-toolbar);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
  min-height: 44px;
  position: relative;
  transition:
    padding var(--v6-motion-fast) var(--v6-ease-out),
    background var(--v6-motion-base) var(--v6-ease-out),
    min-height var(--v6-motion-fast) var(--v6-ease-out);
}

.mac-toolbar--compact {
  padding: var(--v6-space-1) var(--v6-space-3);
  min-height: 32px;
}

.mac-toolbar--bordered.mac-toolbar--top {
  border-top: 1px solid var(--v6-color-border);
}

.mac-toolbar--bordered.mac-toolbar--bottom {
  border-bottom: 1px solid var(--v6-color-border);
}

.mac-toolbar--bordered.mac-toolbar--both {
  border-top: 1px solid var(--v6-color-border);
  border-bottom: 1px solid var(--v6-color-border);
}

.mac-toolbar--transparent {
  background: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

.mac-toolbar--transparent.mac-toolbar--top {
  border-top-color: transparent;
}

.mac-toolbar--transparent.mac-toolbar--bottom {
  border-bottom-color: transparent;
}

.mac-toolbar--transparent.mac-toolbar--both {
  border-top-color: transparent;
  border-bottom-color: transparent;
}

.mac-toolbar__leading,
.mac-toolbar__trailing {
  display: flex;
  align-items: center;
  gap: var(--v6-space-1);
  flex-shrink: 0;
}

.mac-toolbar__center {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  flex: 1;
  min-width: 0;
}

.mac-toolbar__leading {
  margin-right: auto;
}

.mac-toolbar__trailing {
  margin-left: auto;
}

.mac-toolbar :deep(.v6-button-group) {
  display: flex;
  gap: var(--v6-space-1);
}

.mac-toolbar :deep(button),
.mac-toolbar :deep(.ant-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--v6-space-1);
}

:root[data-perf-mode='low'] .mac-toolbar {
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  background: var(--v6-color-surface);
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .mac-toolbar {
    transition: none;
  }
}
</style>
