<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  baahInstallPrompts,
  baahInstallDecisionPending,
  respondToBAAHInstallRecovery,
} from '@/services/baahInstallRecovery'

const { t } = useI18n()
const prompt = computed(() => baahInstallPrompts.value[0] ?? null)
const acknowledged = ref(false)
const sendFailed = ref(false)
const submitting = computed(() => baahInstallDecisionPending.value === prompt.value?.requestId)

watch(
  () => prompt.value?.requestId,
  () => {
    acknowledged.value = false
    sendFailed.value = false
  }
)

function decide(action: 'retry' | 'skip' | 'stop') {
  if (submitting.value || (action === 'skip' && !acknowledged.value)) return
  sendFailed.value = !respondToBAAHInstallRecovery(action)
}
</script>

<template>
  <a-modal
    :open="Boolean(prompt)"
    :title="t('bootstrap.comp.baahRecoveryTitle')"
    :closable="false"
    :keyboard="false"
    :mask-closable="false"
    :footer="null"
    :z-index="900"
    :width="560"
    class="baah-recovery-modal"
    centered
  >
    <template v-if="prompt">
      <p>{{ t('bootstrap.comp.baahRecoveryMessage') }}</p>
      <a-descriptions bordered :column="1" size="small" class="recovery-details">
        <a-descriptions-item :label="t('bootstrap.comp.baahRecoveryManagedName')">
          {{ prompt.managedName || t('bootstrap.comp.baahRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.baahRecoveryInstallPath')">
          <span class="recovery-path">{{
            prompt.installPath || t('bootstrap.comp.baahRecoveryUnknown')
          }}</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.baahRecoveryCurrent')">
          {{ prompt.installedVersion || t('bootstrap.comp.baahRecoveryUnknown') }}
        </a-descriptions-item>
                        <a-descriptions-item :label="t('bootstrap.comp.baahRecoveryTakeover')">
          {{
            t(
              prompt.takeoverEnabled
                ? 'bootstrap.comp.baahRecoveryEnabled'
                : 'bootstrap.comp.baahRecoveryDisabled'
            )
          }}
        </a-descriptions-item>
      </a-descriptions>
      <a-alert
        class="recovery-warning"
        type="warning"
        show-icon
        :message="t('bootstrap.comp.baahRecoveryRisk')"
      />
      <a-checkbox
        v-if="prompt.canSkip"
        v-model:checked="acknowledged"
        :disabled="submitting"
        class="recovery-check"
      >
        {{ t('bootstrap.comp.baahRecoveryAcknowledgement') }}
      </a-checkbox>
      <a-alert
        v-if="sendFailed"
        class="recovery-error"
        type="error"
        show-icon
        :message="t('bootstrap.comp.baahRecoverySendFailed')"
      />
      <a-alert
        v-if="!prompt.canSkip"
        class="recovery-warning"
        type="info"
        show-icon
        :message="t('bootstrap.comp.baahRecoveryCannotSkip')"
      />
      <div class="recovery-actions">
        <a-button :disabled="submitting" @click="decide('stop')">
          {{ t('bootstrap.comp.baahRecoveryStop') }}
        </a-button>
        <a-button type="primary" :loading="submitting" @click="decide('retry')">
          {{ t('bootstrap.comp.baahRecoveryRetry') }}
        </a-button>
        <a-button v-if="prompt.canSkip" danger :disabled="!acknowledged || submitting" @click="decide('skip')">
          {{ t('bootstrap.comp.baahRecoverySkip') }}
        </a-button>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
:global(.baah-recovery-modal .ant-modal-body) {
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
.recovery-check,
.recovery-error {
  margin-top: 12px;
}

.recovery-check {
  display: block;
}

.recovery-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}
</style>
