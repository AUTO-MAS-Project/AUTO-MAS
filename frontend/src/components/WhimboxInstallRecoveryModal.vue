<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  whimboxInstallPrompts,
  whimboxInstallDecisionPending,
  respondToWhimboxInstallRecovery,
} from '@/services/whimboxInstallRecovery'

const { t } = useI18n()
const prompt = computed(() => whimboxInstallPrompts.value[0] ?? null)
const acknowledged = ref(false)
const sendFailed = ref(false)
const submitting = computed(() => whimboxInstallDecisionPending.value === prompt.value?.requestId)

watch(
  () => prompt.value?.requestId,
  () => {
    acknowledged.value = false
    sendFailed.value = false
  }
)

function decide(action: 'retry' | 'skip' | 'stop' | 'repair_gui') {
  if (submitting.value || (action === 'skip' && !acknowledged.value)) return
  sendFailed.value = !respondToWhimboxInstallRecovery(action)
}
</script>

<template>
  <a-modal
    :open="Boolean(prompt)"
    :title="t('bootstrap.comp.whimboxRecoveryTitle')"
    :closable="false"
    :keyboard="false"
    :mask-closable="false"
    :footer="null"
    :z-index="900"
    :width="560"
    class="whimbox-recovery-modal"
    centered
  >
    <template v-if="prompt">
      <p>{{ t('bootstrap.comp.whimboxRecoveryMessage') }}</p>
      <a-descriptions bordered :column="1" size="small" class="recovery-details">
        <a-descriptions-item :label="t('bootstrap.comp.whimboxRecoveryManagedName')">
          {{ prompt.managedName || t('bootstrap.comp.whimboxRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.whimboxRecoveryInstallPath')">
          <span class="recovery-path">{{
            prompt.installPath || t('bootstrap.comp.whimboxRecoveryUnknown')
          }}</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.whimboxRecoveryCurrent')">
          {{ prompt.installedVersion || t('bootstrap.comp.whimboxRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.whimboxRecoveryTarget')">
          {{ prompt.targetVersion || t('bootstrap.comp.whimboxRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.whimboxRecoveryTakeover')">
          {{
            t(
              prompt.takeoverEnabled
                ? 'bootstrap.comp.whimboxRecoveryEnabled'
                : 'bootstrap.comp.whimboxRecoveryDisabled'
            )
          }}
        </a-descriptions-item>
      </a-descriptions>
      <a-alert
        class="recovery-warning"
        type="warning"
        show-icon
        :message="t('bootstrap.comp.whimboxRecoveryRisk')"
      />
      <a-checkbox v-model:checked="acknowledged" :disabled="submitting" class="recovery-check">
        {{ t('bootstrap.comp.whimboxRecoveryAcknowledgement') }}
      </a-checkbox>
      <a-alert
        v-if="sendFailed"
        class="recovery-error"
        type="error"
        show-icon
        :message="t('bootstrap.comp.whimboxRecoverySendFailed')"
      />
      <div class="recovery-actions">
        <a-button
          v-if="prompt.canOpenOfficialApp"
          :disabled="submitting"
          @click="decide('repair_gui')"
        >
          {{ t('bootstrap.comp.whimboxRecoveryRepairGui') }}
        </a-button>
        <a-button :disabled="submitting" @click="decide('stop')">
          {{ t('bootstrap.comp.whimboxRecoveryStop') }}
        </a-button>
        <a-button type="primary" :loading="submitting" @click="decide('retry')">
          {{ t('bootstrap.comp.whimboxRecoveryRetry') }}
        </a-button>
        <a-button danger :disabled="!acknowledged || submitting" @click="decide('skip')">
          {{ t('bootstrap.comp.whimboxRecoverySkip') }}
        </a-button>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
:global(.whimbox-recovery-modal .ant-modal-body) {
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
