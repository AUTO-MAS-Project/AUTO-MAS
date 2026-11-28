<script setup lang="ts">
import AppPage from '@/components/ui/AppPage.vue'
import PageSurface from '@/components/PageSurface.vue'
import StateView from '@/components/ui/StateView.vue'

/**
 * 脚本/用户配置编辑页统一外壳。
 *
 * 负责页头、锁定/提示横幅、加载错误态、正文表面容器与会话遮罩插槽的统一排布，
 * 避免各编辑页重复定义外层容器与表单卡片样式。
 */
withDefaults(
  defineProps<{
    loading?: boolean
    error?: string | null
    loadingTip?: string
    maxWidth?: number | string
    fixedHeader?: boolean
    /** 默认由内部 PageSurface 承载表单；若页面仍由 ConfigLockPanel + a-card 承载，可置为 false */
    surface?: boolean
  }>(),
  {
    loading: false,
    error: null,
    loadingTip: undefined,
    maxWidth: undefined,
    fixedHeader: false,
    surface: true,
  }
)

const emit = defineEmits<{
  retry: []
}>()
</script>

<template>
  <AppPage
    class="config-edit-shell"
    :layout="fixedHeader ? 'fill' : 'scroll'"
    :max-width="maxWidth"
  >
    <div v-if="$slots.header" class="config-edit-shell__header">
      <slot name="header" />
    </div>

    <div :class="fixedHeader ? 'config-edit-shell__scroll-area' : 'config-edit-shell__flow'">
      <div v-if="$slots.banner" class="config-edit-shell__banner">
        <slot name="banner" />
      </div>

      <StateView
        :loading="loading"
        :error="error"
        :empty="Boolean(error)"
        :loading-tip="loadingTip"
        @retry="emit('retry')"
      >
        <PageSurface v-if="surface" :scrollable="false" class="config-edit-shell__surface">
          <slot />
        </PageSurface>
        <div v-else class="config-edit-shell__body">
          <slot />
        </div>
      </StateView>
    </div>

    <div v-if="$slots.footer" class="config-edit-shell__footer">
      <slot name="footer" />
    </div>

    <slot name="overlay" />
  </AppPage>
</template>

<style scoped>
.config-edit-shell {
  gap: 0;
}

.config-edit-shell__flow {
  display: contents;
}

.config-edit-shell__scroll-area {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior-y: contain;
}

.config-edit-shell__banner {
  margin-bottom: 16px;
}

.config-edit-shell__surface,
.config-edit-shell__body {
  min-width: 0;
}

.config-edit-shell__footer {
  margin-top: 16px;
}
</style>
