<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  srcInstallPrompts,
  srcInstallDecisionPending,
  respondToSrcInstallRecovery,
} from '@/services/srcInstallRecovery'

const { t } = useI18n()
const prompt = computed(() => srcInstallPrompts.value[0] ?? null)
const acknowledged = ref(false)
const sendFailed = ref(false)
const submitting = computed(() => srcInstallDecisionPending.value === prompt.value?.requestId)

watch(
  () => prompt.value?.requestId,
  () => {
    acknowledged.value = false
    sendFailed.value = false
  }
)

function decide(action: 'retry' | 'skip' | 'stop') {
  if (submitting.value || (action === 'skip' && !acknowledged.value)) return
  sendFailed.value = !respondToSrcInstallRecovery(action)
}
</script>

<template>
  <a-modal
    :open="Boolean(prompt)"
    :title="t('bootstrap.comp.srcRecoveryTitle')"
    :closable="false"
    :keyboard="false"
    :mask-closable="false"
    :footer="null"
    :z-index="900"
    :width="560"
    class="src-recovery-modal"
    centered
  >
    <template v-if="prompt">
      <p>{{ t('bootstrap.comp.srcRecoveryMessage') }}</p>
      <a-descriptions bordered :column="1" size="small" class="recovery-details">
        <a-descriptions-item :label="t('bootstrap.comp.srcRecoveryManagedName')">
          {{ prompt.managedName || t('bootstrap.comp.srcRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.srcRecoveryInstallPath')">
          <span class="recovery-path">{{
            prompt.installPath || t('bootstrap.comp.srcRecoveryUnknown')
          }}</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.srcRecoveryCurrent')">
          {{ prompt.installedVersion || t('bootstrap.comp.srcRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.srcRecoveryTarget')">
          {{ prompt.targetVersion || t('bootstrap.comp.srcRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.srcRecoveryTakeover')">
          {{
            t(
              prompt.takeoverEnabled
                ? 'bootstrap.comp.srcRecoveryEnabled'
                : 'bootstrap.comp.srcRecoveryDisabled'
            )
          }}
        </a-descriptions-item>
      </a-descriptions>
      <a-alert
        class="recovery-warning"
        type="warning"
        show-icon
        :message="t('bootstrap.comp.srcRecoveryRisk')"
      />
      <a-checkbox v-model:checked="acknowledged" :disabled="submitting" class="recovery-check">
        {{ t('bootstrap.comp.srcRecoveryAcknowledgement') }}
      </a-checkbox>
      <a-alert
        v-if="sendFailed"
        class="recovery-error"
        type="error"
        show-icon
        :message="t('bootstrap.comp.srcRecoverySendFailed')"
      />
      <div class="recovery-actions">
        <a-button :disabled="submitting" @click="decide('stop')">
          {{ t('bootstrap.comp.srcRecoveryStop') }}
        </a-button>
        <a-button type="primary" :loading="submitting" @click="decide('retry')">
          {{ t('bootstrap.comp.srcRecoveryRetry') }}
        </a-button>
        <a-button danger :disabled="!acknowledged || submitting" @click="decide('skip')">
          {{ t('bootstrap.comp.srcRecoverySkip') }}
        </a-button>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
:global(.src-recovery-modal .ant-modal-body) {
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
