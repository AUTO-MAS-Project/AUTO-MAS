<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    icon?: unknown
  }>(),
  { icon: undefined }
)
</script>

<template>
  <header class="app-page-header">
    <div class="page-header-main">
      <slot name="leading" />
      <h1 class="app-page-title">
        <component :is="icon" v-if="icon" />
        {{ title }}
      </h1>
    </div>
    <div class="page-header-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header-main,
.page-header-actions {
  display: flex;
  align-items: center;
  min-width: 0;
}

.page-header-main {
  gap: 8px;
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
