<script setup lang="ts">
import type { Component } from 'vue'

withDefaults(
  defineProps<{
    title?: string
    subtitle?: string
    icon?: Component | unknown
  }>(),
  {
    title: '',
    subtitle: undefined,
    icon: undefined,
  }
)
</script>

<template>
  <header class="app-page-header">
    <div class="page-header-main">
      <slot name="leading" />
      <div class="page-header-heading">
        <div class="page-header-title-row">
          <slot name="title">
            <h1 class="app-page-title">
              <component :is="icon" v-if="icon" />
              {{ title }}
            </h1>
          </slot>
          <div v-if="$slots.meta" class="page-header-meta">
            <slot name="meta" />
          </div>
          <div v-if="$slots.search" class="page-header-search">
            <slot name="search" />
          </div>
        </div>
        <p v-if="subtitle" class="page-header-subtitle">{{ subtitle }}</p>
      </div>
    </div>
    <div v-if="$slots.actions" class="page-header-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header-main,
.page-header-actions,
.page-header-title-row,
.page-header-meta {
  display: flex;
  align-items: center;
  min-width: 0;
}

.page-header-main {
  gap: 8px;
  flex: 1;
}

.page-header-heading {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.page-header-title-row {
  flex-wrap: wrap;
  gap: 12px;
}

.page-header-meta {
  gap: 8px;
}

.page-header-search {
  min-width: 0;
}

.page-header-subtitle {
  margin: 4px 0 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.page-header-actions {
  flex-shrink: 0;
  gap: 8px;
}

@media (max-width: 768px) {
  .page-header-actions {
    justify-content: flex-end;
    flex-wrap: wrap;
  }
}
</style>
