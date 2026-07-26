<template>
  <!-- shell 声明容器:header 自身的窄屏规则由它驱动
       (@container 不能命中声明容器的元素自身,且 PageHeader 全站使用,
       不能依赖某个页面的外层容器) -->
  <div class="mac-page-header-shell">
    <header
      class="mac-page-header"
      :class="{
        'mac-page-header--bordered': bordered,
        'mac-page-header--transparent': transparent,
        'mac-page-header--compact': compact,
      }"
      role="banner"
    >
      <div class="mac-page-header__content">
        <div class="mac-page-header__title-group">
          <slot name="title">
            <h1 class="mac-page-header__title">{{ title }}</h1>
          </slot>
          <slot name="subtitle">
            <p v-if="subtitle" class="mac-page-header__subtitle">{{ subtitle }}</p>
          </slot>
        </div>
        <div v-if="$slots.default" class="mac-page-header__aside">
          <slot />
        </div>
      </div>
      <div v-if="$slots.actions" class="mac-page-header__actions">
        <slot name="actions" />
      </div>
    </header>
  </div>
</template>

<script setup lang="ts">
interface Props {
  title: string
  subtitle?: string
  bordered?: boolean
  transparent?: boolean
  compact?: boolean
}

withDefaults(defineProps<Props>(), {
  subtitle: undefined,
  bordered: true,
  transparent: false,
  compact: false,
})
</script>

<style scoped>
.mac-page-header-shell {
  container: mac-page-header / inline-size;
  min-width: 0;
}

.mac-page-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-4);
  padding: var(--v6-space-6) var(--v6-content-padding-inline);
  background: var(--v6-vibrancy-titlebar);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
  border-bottom: 1px solid var(--v6-color-border);
  transition:
    padding var(--v6-motion-fast) var(--v6-ease-out),
    background var(--v6-motion-base) var(--v6-ease-out),
    border-color var(--v6-motion-fast) var(--v6-ease-out);
}

.mac-page-header--bordered {
  border-bottom-color: var(--v6-color-border);
}

.mac-page-header--transparent {
  background: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  border-bottom-color: transparent;
}

.mac-page-header--compact {
  padding: var(--v6-space-3) var(--v6-content-padding-inline);
}

.mac-page-header__content {
  display: flex;
  align-items: center;
  gap: var(--v6-space-4);
  flex: 1 1 320px;
  min-width: 0;
}

.mac-page-header__title-group {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-0-5);
  min-width: 0;
}

.mac-page-header__title {
  margin: 0;
  font-size: var(--v6-font-size-3xl);
  font-weight: var(--v6-font-weight-semibold);
  line-height: var(--v6-line-height-tight);
  color: var(--v6-color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: font-size var(--v6-motion-fast) var(--v6-ease-out);
}

.mac-page-header--compact .mac-page-header__title {
  font-size: var(--v6-font-size-xl);
}

.mac-page-header__subtitle {
  margin: 0;
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-normal);
  line-height: var(--v6-line-height-normal);
  color: var(--v6-color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mac-page-header__aside {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  margin-left: auto;
}

.mac-page-header__actions {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  flex-shrink: 0;
}

/* 按 header 实际可用宽度响应(侧栏挤压时同样生效),不用视口 @media */
@container mac-page-header (max-width: 720px) {
  .mac-page-header {
    align-items: flex-start;
    gap: var(--v6-space-3);
    padding: var(--v6-space-4) var(--v6-content-padding-inline);
  }

  .mac-page-header__content {
    flex-basis: 100%;
    align-items: flex-start;
  }

  .mac-page-header__aside {
    margin-left: 0;
  }

  .mac-page-header__actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .mac-page-header__subtitle {
    white-space: normal;
  }
}
:root[data-perf-mode='low'] .mac-page-header {
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  background: var(--v6-color-titlebar);
  transition: none;
}

:root[data-perf-mode='low'] .mac-page-header__title {
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .mac-page-header,
  .mac-page-header__title {
    transition: none;
  }
}
</style>
