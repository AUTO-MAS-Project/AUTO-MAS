<template>
  <section class="page-surface">
    <slot />
  </section>
</template>

<style scoped>
.page-surface {
  flex: 1;
  width: 100%;
  min-height: 0;
  padding: 16px;
  overflow: auto;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}
</style>
