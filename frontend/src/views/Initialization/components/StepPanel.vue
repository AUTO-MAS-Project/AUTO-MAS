<template>
  <RuntimeSetupPanel v-bind="forwardedProps" />
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import RuntimeSetupPanel from './RuntimeSetupPanel.vue'
import type { RuntimeDoctorCheck } from '@/types/electron'
import type { MirrorConfig } from '@/types/mirror'
import type { FailureAction, FailureNoticeKind } from '@/utils/initializationDecision'

defineOptions({
  name: 'InitializationStepPanel',
  inheritAttrs: false,
})

interface Props {
  title: string
  status: 'waiting' | 'processing' | 'success' | 'failed'
  message: string
  progress?: number
  progressIndeterminate?: boolean
  elapsedText?: string
  showMirrorSelection?: boolean
  showSkipButton?: boolean
  mirrors?: MirrorConfig[]
  selectedMirror?: string
  countdown?: number
  failureActions?: FailureAction[]
  failureNotice?: FailureNoticeKind | null
  failureLogs?: string
  doctorChecks?: RuntimeDoctorCheck[] | null
  doctorRunning?: boolean
}

const props = defineProps<Props>()
const attrs = useAttrs()
const forwardedProps = computed(() => ({ ...props, ...attrs }))
</script>
