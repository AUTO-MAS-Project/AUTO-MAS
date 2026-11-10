<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  maaResourceRecoveryPrompts,
  maaResourceRecoveryDecisionPending,
  respondToMAAResourceRecovery,
} from '@/services/maaResourceRecovery'

const { t } = useI18n()
const prompt = computed(() => maaResourceRecoveryPrompts.value[0] ?? null)
const sendFailed = ref(false)
const submitting = computed(
  () => maaResourceRecoveryDecisionPending.value === prompt.value?.requestId
)

watch(
  () => prompt.value?.requestId,
  () => {
    sendFailed.value = false
  }
)

function decide(action: 'retry' | 'stop') {
  if (submitting.value) return
  sendFailed.value = !respondToMAAResourceRecovery(action)
}
</script>

<template>
  <a-modal
    :open="Boolean(prompt)"
    :title="t('bootstrap.comp.maaResourceRecoveryTitle')"
    :closable="false"
    :keyboard="false"
    :mask-closable="false"
    :footer="null"
    :z-index="900"
    :width="560"
    class="maa-recovery-modal"
    centered
  >
    <template v-if="prompt">
      <p>{{ t('bootstrap.comp.maaResourceRecoveryMessage') }}</p>
      <a-descriptions bordered :column="1" size="small" class="recovery-details">
        <a-descriptions-item :label="t('bootstrap.comp.maaResourceRecoveryManagedName')">
          {{ prompt.managedName || t('bootstrap.comp.maaResourceRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.maaResourceRecoveryInstallPath')">
          <span class="recovery-path">{{
            prompt.installPath || t('bootstrap.comp.maaResourceRecoveryUnknown')
          }}</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.maaResourceRecoveryCurrent')">
          {{ prompt.installedVersion || t('bootstrap.comp.maaResourceRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.maaResourceRecoveryTarget')">
          {{ prompt.targetVersion || t('bootstrap.comp.maaResourceRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.maaResourceRecoveryTakeover')">
          {{
            t(
              prompt.takeoverEnabled
                ? 'bootstrap.comp.maaResourceRecoveryEnabled'
                : 'bootstrap.comp.maaResourceRecoveryDisabled'
            )
          }}
        </a-descriptions-item>
      </a-descriptions>
      <a-alert
        class="recovery-warning"
        type="warning"
        show-icon
        :message="t('bootstrap.comp.maaResourceRecoveryRisk')"
      />
      <a-alert
        v-if="sendFailed"
        class="recovery-error"
        type="error"
        show-icon
        :message="t('bootstrap.comp.maaResourceRecoverySendFailed')"
      />
      <div class="recovery-actions">
        <a-button :disabled="submitting" @click="decide('stop')">
          {{ t('bootstrap.comp.maaResourceRecoveryStop') }}
        </a-button>
        <a-button type="primary" :loading="submitting" @click="decide('retry')">
          {{ t('bootstrap.comp.maaResourceRecoveryRetry') }}
        </a-button>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
:global(.maa-recovery-modal .ant-modal-body) {
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
