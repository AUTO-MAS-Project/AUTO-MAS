<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  bettergiInstallPrompts,
  bettergiInstallDecisionPending,
  respondToBetterGIInstallRecovery,
} from '@/services/bettergiInstallRecovery'

const { t } = useI18n()
const prompt = computed(() => bettergiInstallPrompts.value[0] ?? null)
const acknowledged = ref(false)
const sendFailed = ref(false)
const submitting = computed(() => bettergiInstallDecisionPending.value === prompt.value?.requestId)

watch(
  () => prompt.value?.requestId,
  () => {
    acknowledged.value = false
    sendFailed.value = false
  }
)

function decide(action: 'retry' | 'skip' | 'stop') {
  if (submitting.value || (action === 'skip' && !acknowledged.value)) return
  sendFailed.value = !respondToBetterGIInstallRecovery(action)
}
</script>

<template>
  <a-modal
    :open="Boolean(prompt)"
    :title="t('bootstrap.comp.bettergiRecoveryTitle')"
    :closable="false"
    :keyboard="false"
    :mask-closable="false"
    :footer="null"
    :z-index="900"
    :width="560"
    class="bettergi-recovery-modal"
    centered
  >
    <template v-if="prompt">
      <p>{{ t('bootstrap.comp.bettergiRecoveryMessage') }}</p>
      <a-descriptions bordered :column="1" size="small" class="recovery-details">
        <a-descriptions-item :label="t('bootstrap.comp.bettergiRecoveryManagedName')">
          {{ prompt.managedName || t('bootstrap.comp.bettergiRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.bettergiRecoveryInstallPath')">
          <span class="recovery-path">{{
            prompt.installPath || t('bootstrap.comp.bettergiRecoveryUnknown')
          }}</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.bettergiRecoveryCurrent')">
          {{ prompt.installedVersion || t('bootstrap.comp.bettergiRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.bettergiRecoveryTarget')">
          {{ prompt.targetVersion || t('bootstrap.comp.bettergiRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.bettergiRecoveryChannel')">
          {{
            prompt.channel === 'stable'
              ? t('bootstrap.comp.bettergiRecoveryStable')
              : t('bootstrap.comp.bettergiRecoveryBeta')
          }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.bettergiRecoveryTakeover')">
          {{
            t(
              prompt.takeoverEnabled
                ? 'bootstrap.comp.bettergiRecoveryEnabled'
                : 'bootstrap.comp.bettergiRecoveryDisabled'
            )
          }}
        </a-descriptions-item>
      </a-descriptions>
      <a-alert
        class="recovery-warning"
        type="warning"
        show-icon
        :message="t('bootstrap.comp.bettergiRecoveryRisk')"
      />
      <a-checkbox v-model:checked="acknowledged" :disabled="submitting" class="recovery-check">
        {{ t('bootstrap.comp.bettergiRecoveryAcknowledgement') }}
      </a-checkbox>
      <a-alert
        v-if="sendFailed"
        class="recovery-error"
        type="error"
        show-icon
        :message="t('bootstrap.comp.bettergiRecoverySendFailed')"
      />
      <div class="recovery-actions">
        <a-button :disabled="submitting" @click="decide('stop')">
          {{ t('bootstrap.comp.bettergiRecoveryStop') }}
        </a-button>
        <a-button type="primary" :loading="submitting" @click="decide('retry')">
          {{ t('bootstrap.comp.bettergiRecoveryRetry') }}
        </a-button>
        <a-button danger :disabled="!acknowledged || submitting" @click="decide('skip')">
          {{ t('bootstrap.comp.bettergiRecoverySkip') }}
        </a-button>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
:global(.bettergi-recovery-modal .ant-modal-body) {
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
