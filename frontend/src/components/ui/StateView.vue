<script setup lang="ts">
import { computed } from 'vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import NoData, { type NoDataSize } from '@/components/NoData.vue'

/**
 * 统一面板/页面四态容器（加载、错误重试、空态、正文）。
 *
 * 加载态固定最小可视高度并居中，避免空容器被压缩成 0px 导致 spinner 漂移至左上角。
 */
const props = withDefaults(
  defineProps<{
    loading?: boolean
    error?: string | null
    empty?: boolean
    loadingTip?: string
    emptyTitle?: string
    emptyDescription?: string
    emptySize?: NoDataSize
    minHeight?: number | string
    /** 加载已有数据时是否保留正文并叠加旋转遮罩 */
    overlayLoading?: boolean
  }>(),
  {
    loading: false,
    error: null,
    empty: false,
    loadingTip: undefined,
    emptyTitle: undefined,
    emptyDescription: undefined,
    emptySize: 'md',
    minHeight: 180,
    overlayLoading: false,
  }
)

const emit = defineEmits<{
  retry: []
}>()

const stateBoxStyle = computed(() => ({
  minHeight: typeof props.minHeight === 'number' ? `${props.minHeight}px` : props.minHeight,
}))
</script>

<template>
  <div class="state-view">
    <div
      v-if="loading && (!overlayLoading || empty)"
      class="state-view-center"
      :style="stateBoxStyle"
    >
      <slot name="loading">
        <a-spin :tip="loadingTip" />
      </slot>
    </div>

    <div v-else-if="error && empty" class="state-view-center" :style="stateBoxStyle">
      <div class="state-view-alert">
        <slot name="error" :error="error" :retry="() => emit('retry')">
          <ApiRetryAlert :error="error" :loading="loading" @retry="emit('retry')" />
        </slot>
      </div>
    </div>

    <div v-else-if="empty" class="state-view-center empty-state" :style="stateBoxStyle">
      <slot name="empty">
        <NoData :title="emptyTitle" :description="emptyDescription" :size="emptySize">
          <slot name="empty-action" />
        </NoData>
      </slot>
    </div>

    <template v-else>
      <div v-if="error" class="state-view-banner">
        <slot name="error" :error="error" :retry="() => emit('retry')">
          <ApiRetryAlert :error="error" :loading="loading" @retry="emit('retry')" />
        </slot>
      </div>
      <a-spin
        v-if="overlayLoading"
        :spinning="loading"
        :tip="loadingTip"
        wrapper-class-name="state-view-spin"
      >
        <slot />
      </a-spin>
      <slot v-else />
    </template>
  </div>
</template>

<style scoped>
.state-view {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.state-view-center {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
}

.state-view-alert {
  width: 100%;
  max-width: 520px;
}

.state-view-banner {
  margin-bottom: 12px;
}

.state-view :deep(.state-view-spin),
.state-view :deep(.state-view-spin > .ant-spin-container) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}
</style>
