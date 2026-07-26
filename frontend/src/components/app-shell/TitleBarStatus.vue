<script setup lang="ts">
import { computed } from 'vue'
import { LoadingOutlined } from '@ant-design/icons-vue'

export interface TitleBarStatusProps {
  isBootstrapping?: boolean
  downloadHint?: string
  updateInfo?: { if_need_update?: boolean; latest_version?: string } | null
  backendUpdateInfo?: { if_need_update?: boolean } | null
}

const props = defineProps<TitleBarStatusProps>()

const emit = defineEmits<{
  (e: 'open-download'): void
  (e: 'open-app-update'): void
  (e: 'open-backend-update'): void
}>()

const updateVersion = computed(() => props.updateInfo?.latest_version ?? '')
</script>

<template>
  <div class="title-bar-status" role="status" aria-live="polite">
    <span v-if="isBootstrapping" class="startup-status" aria-label="后端启动中">
      <LoadingOutlined aria-hidden="true" />
      后端启动中
    </span>

    <span
      v-if="downloadHint"
      class="update-hint clickable"
      role="button"
      tabindex="0"
      :aria-label="downloadHint"
      @click="emit('open-download')"
      @keydown.enter.prevent="emit('open-download')"
      @keydown.space.prevent="emit('open-download')"
    >
      {{ downloadHint }}
    </span>

    <span
      v-else-if="updateInfo?.if_need_update"
      class="update-hint clickable"
      role="button"
      tabindex="0"
      :aria-label="`检测到更新 ${updateVersion}，请尽快更新`"
      @click="emit('open-app-update')"
      @keydown.enter.prevent="emit('open-app-update')"
      @keydown.space.prevent="emit('open-app-update')"
    >
      检测到更新 {{ updateVersion }} 请尽快更新
    </span>

    <span
      v-if="backendUpdateInfo?.if_need_update"
      class="update-hint clickable"
      role="button"
      tabindex="0"
      aria-label="检测到后端更新，点击以更新后端"
      @click="emit('open-backend-update')"
      @keydown.enter.prevent="emit('open-backend-update')"
      @keydown.space.prevent="emit('open-backend-update')"
    >
      检测到后端更新，点击以更新后端
    </span>
  </div>
</template>

<style scoped>
.title-bar-status {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  height: 100%;
  padding: 0 var(--v6-space-2);
  user-select: none;
  -webkit-user-select: none;
}

.startup-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--ant-color-primary);
  font-size: 13px;
}

.update-hint {
  font-weight: 600;
  font-size: 13px;
  line-height: 1.2;
  cursor: help;
  color: var(--v6-color-warning);
  transition: color var(--v6-motion-fast) var(--v6-ease-out);
}

.update-hint.clickable {
  cursor: pointer;
  user-select: none;
  -webkit-app-region: no-drag;
}

.update-hint.clickable:hover {
  color: var(--v6-color-error);
}

.update-hint.clickable:focus {
  outline: none;
  box-shadow: none;
}

.update-hint.clickable:focus-visible {
  box-shadow: var(--v6-focus-ring-inset);
  border-radius: var(--v6-radius-control);
}

.update-hint + .update-hint {
  margin-left: 12px;
}
</style>
