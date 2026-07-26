<script setup lang="ts">
import { LoadingOutlined } from '@ant-design/icons-vue'

defineProps<{
  hmrOverlayVisible: boolean
  hmrOverlayText: string
}>()
</script>

<template>
  <a-layout class="app-main-layout">
    <a-layout-content
      id="app-main-content"
      class="content-area"
      tabindex="-1"
      aria-label="主内容区"
    >
      <router-view v-slot="{ Component, route: viewRoute }">
        <keep-alive :include="['Scheduler']">
          <component :is="Component" :key="viewRoute.path" />
        </keep-alive>
      </router-view>

      <transition name="hmr-fade">
        <div v-if="hmrOverlayVisible" class="hmr-soft-overlay" aria-live="polite">
          <div class="hmr-soft-panel">
            <LoadingOutlined class="hmr-soft-spinner" />
            <span>{{ hmrOverlayText }}</span>
          </div>
        </div>
      </transition>
    </a-layout-content>
  </a-layout>
</template>

<style scoped>
.app-main-layout {
  flex: 1;
  min-width: 0;
  container: app-content / inline-size;
  background: transparent;
  position: relative;
  z-index: var(--v6-z-content);
}

.content-area {
  position: relative;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  overflow: auto;
  overscroll-behavior: contain;
  scrollbar-width: none;
  -ms-overflow-style: none;
  padding: var(--v6-content-padding-block) var(--v6-content-padding-inline)
    var(--v6-content-padding-block);
  background: transparent;
}

.content-area > * {
  min-width: 0;
}

.content-area::-webkit-scrollbar {
  display: none;
}

.hmr-soft-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--v6-z-global-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--v6-space-6);
  background: color-mix(in srgb, var(--ant-color-bg-layout) 70%, transparent);
  backdrop-filter: blur(4px);
  pointer-events: none;
}

.hmr-soft-panel {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 10px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--v6-radius-card);
  color: var(--v6-color-text);
  background: var(--v6-color-surface-elevated);
  box-shadow: var(--v6-shadow-elevated);
  font-size: 14px;
  line-height: 1.4;
}

.hmr-soft-spinner {
  color: var(--ant-color-primary);
  font-size: 18px;
}

.hmr-fade-enter-active,
.hmr-fade-leave-active {
  transition:
    opacity var(--v6-motion-fast) var(--v6-ease-out),
    backdrop-filter var(--v6-motion-fast) var(--v6-ease-out);
}

.hmr-fade-enter-from,
.hmr-fade-leave-to {
  opacity: 0;
  backdrop-filter: blur(0);
}

@media (max-width: 720px) {
  .content-area {
    padding: var(--v6-content-padding-block) var(--v6-content-padding-inline);
  }
}

@media (prefers-reduced-motion: reduce) {
  .hmr-fade-enter-active,
  .hmr-fade-leave-active {
    transition: none;
  }
}
</style>
