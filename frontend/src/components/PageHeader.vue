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
  <header class="page-header">
    <div class="page-header-main">
      <slot name="leading" />
      <h1 class="page-title">
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
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 0 4px;
}

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

.page-title {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 32px;
  font-weight: 700;
  line-height: 1.25;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

@media (max-width: 768px) {
  .page-header {
    align-items: stretch;
    flex-direction: column;
    gap: 12px;
    padding: 0 2px;
  }

  .page-header-actions {
    justify-content: flex-end;
    flex-wrap: wrap;
  }

  .page-title {
    font-size: 24px;
  }
}
</style>
