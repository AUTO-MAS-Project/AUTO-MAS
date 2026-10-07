<template>
  <!-- 读屏：role=status + aria-live 让「保存中/已保存/保存失败」被念出来 -->
  <a-tag
    :color="color"
    :data-state="state"
    class="save-state-indicator"
    role="status"
    aria-live="polite"
  >
    {{ t(saveStateLabelKey(state)) }}
  </a-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { saveStateLabelKey, type SaveState } from '@/utils/saveState'

defineOptions({ name: 'SaveStateIndicator' })

const props = defineProps<{
  state: SaveState
}>()

const { t } = useI18n()

const COLORS: Record<SaveState, string> = {
  idle: 'default',
  dirty: 'warning',
  saving: 'processing',
  saved: 'success',
  failed_draft_kept: 'error',
  failed_reverted: 'error',
  rejected: 'error',
  discarded: 'default',
  unknown: 'warning',
}

const color = computed(() => COLORS[props.state] ?? 'default')
</script>
