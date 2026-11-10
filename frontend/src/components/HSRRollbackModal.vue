<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  hsrRollbackPrompts,
  hsrRollbackDecisionPending,
  respondToHSRRollback,
} from '@/services/hsrRollback'

const { t } = useI18n()
const prompt = computed(() => hsrRollbackPrompts.value[0] ?? null)
const sendFailed = ref(false)
const submitting = computed(() => hsrRollbackDecisionPending.value === prompt.value?.requestId)

watch(
  () => prompt.value?.requestId,
  () => {
    sendFailed.value = false
  }
)

function decide(action: 'retry' | 'stop') {
  if (submitting.value) return
  sendFailed.value = !respondToHSRRollback(action)
}
</script>

<template>
  <a-modal
    :open="Boolean(prompt)"
    :title="t('bootstrap.comp.hsrRollbackTitle')"
    :closable="false"
    :keyboard="false"
    :mask-closable="false"
    :footer="null"
    :z-index="900"
    :width="560"
    class="hsr-recovery-modal"
    centered
  >
    <template v-if="prompt">
      <p>{{ t('bootstrap.comp.hsrRollbackMessage') }}</p>
      <a-descriptions bordered :column="1" size="small" class="recovery-details">
        <a-descriptions-item :label="t('bootstrap.comp.hsrRollbackManagedName')">
          {{ prompt.managedName || t('bootstrap.comp.hsrRollbackUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.hsrRollbackInstallPath')">
          <span class="recovery-path">{{
            prompt.installPath || t('bootstrap.comp.hsrRollbackUnknown')
          }}</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.hsrRollbackEngine')">
          {{ prompt.engine || t('bootstrap.comp.hsrRollbackUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.hsrRollbackReason')">
          <span class="recovery-path">{{ prompt.failure }}</span>
        </a-descriptions-item>
      </a-descriptions>
      <a-alert
        class="recovery-warning"
        type="warning"
        show-icon
        :message="t('bootstrap.comp.hsrRollbackRisk')"
      />
      <a-alert
        v-if="sendFailed"
        class="recovery-error"
        type="error"
        show-icon
        :message="t('bootstrap.comp.hsrRollbackSendFailed')"
      />
      <div class="recovery-actions">
        <a-button :disabled="submitting" @click="decide('stop')">
          {{ t('bootstrap.comp.hsrRollbackStop') }}
        </a-button>
        <a-button type="primary" :loading="submitting" @click="decide('retry')">
          {{ t('bootstrap.comp.hsrRollbackRetry') }}
        </a-button>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
:global(.hsr-recovery-modal .ant-modal-body) {
  max-height: 70vh;
  overflow-y: auto;
}

.recovery-details {
  margin: 16px 0;
}

.recovery-path {
  overflow-wrap: anywhere;
  user-select: text;
}

.recovery-warning,
.recovery-error {
  margin-top: 12px;
}

.recovery-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}
</style>
