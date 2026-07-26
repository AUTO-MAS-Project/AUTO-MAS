<script setup lang="ts">
defineProps<{
  version: string
}>()
</script>

<template>
  <div class="title-bar-brand" aria-label="AUTO-MAS 应用标识">
    <img src="@/assets/AUTO-MAS.ico" alt="AUTO-MAS" class="title-logo" />
    <span class="title-text">AUTO-MAS</span>
    <span class="version-text" aria-label="当前版本">{{ version }}</span>
  </div>
</template>

<style scoped>
.title-bar-brand {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  position: relative;
  height: 100%;
  padding-left: var(--v6-space-3);
  -webkit-app-region: drag;
}

.title-logo {
  width: 20px;
  height: 20px;
  position: relative;
  z-index: 1;
}

.title-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--v6-color-text);
  position: relative;
  z-index: 1;
}

.version-text {
  min-width: 0;
  max-width: min(28vw, 320px);
  overflow: hidden;
  color: var(--v6-color-text-secondary);
  font-size: 13px;
  font-weight: 400;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 680px) {
  .title-bar-brand {
    padding-left: var(--v6-space-2);
  }

  .version-text {
    max-width: 20vw;
  }
}
</style>
