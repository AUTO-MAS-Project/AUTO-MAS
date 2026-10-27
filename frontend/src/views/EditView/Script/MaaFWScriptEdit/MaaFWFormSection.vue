<template>
  <div class="form-section" :class="{ 'form-section--compact': compact }">
    <div class="section-header">
      <h3>{{ title }}</h3>
    </div>
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    compact?: boolean
  }>(),
  {
    compact: false,
  }
)
</script>

<style scoped>
.form-section {
  margin-bottom: 40px;
}

.form-section--compact {
  margin-bottom: 24px;
}

.section-header {
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 700;
}

.section-header h3::before {
  width: 4px;
  height: 20px;
  border-radius: 2px;
  background: var(--ant-color-text-quaternary);
  content: '';
}
</style>
