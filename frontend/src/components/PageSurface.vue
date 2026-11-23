<script setup lang="ts">
import { computed } from 'vue'

/**
 * 统一页面正文表面容器。
 *
 * 复用 styles/pageSurface.css 与 styles/appearanceSurfaces.css 的共享表面类，
 * 自动适配亮/暗主题、自定义背景透明度与嵌套透明去重。
 */
const props = withDefaults(
  defineProps<{
    variant?: 'surface' | 'section' | 'transparent'
    padding?: 'none' | 'sm' | 'md'
    scrollable?: boolean
  }>(),
  {
    variant: 'surface',
    padding: 'md',
    scrollable: true,
  }
)

const surfaceClass = computed(() => [
  'page-surface',
  props.variant === 'surface' ? 'app-page-surface' : null,
  props.variant === 'section' ? 'app-page-section' : null,
  `page-surface--pad-${props.padding}`,
  props.scrollable ? 'page-surface--scrollable' : null,
])
</script>

<template>
  <section :class="surfaceClass">
    <slot />
  </section>
</template>

<style scoped>
.page-surface {
  flex: 1;
  width: 100%;
  min-width: 0;
  min-height: 0;
}

.page-surface--scrollable {
  overflow: auto;
}

.page-surface--pad-none {
  padding: 0;
}

.page-surface--pad-sm {
  padding: 12px;
}

.page-surface--pad-md {
  padding: var(--app-page-content-padding);
}
</style>
