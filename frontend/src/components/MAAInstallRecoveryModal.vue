<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  maaInstallPrompts,
  maaInstallDecisionPending,
  respondToMAAInstallRecovery,
} from '@/services/maaInstallRecovery'

const { t } = useI18n()
const prompt = computed(() => maaInstallPrompts.value[0] ?? null)
const acknowledged = ref(false)
const sendFailed = ref(false)
const submitting = computed(() => maaInstallDecisionPending.value === prompt.value?.requestId)

watch(
  () => prompt.value?.requestId,
  () => {
    acknowledged.value = false
    sendFailed.value = false
  }
)

function decide(action: 'retry' | 'skip' | 'stop') {
  if (submitting.value || (action === 'skip' && !acknowledged.value)) return
  sendFailed.value = !respondToMAAInstallRecovery(action)
}
</script>

<template>
  <a-modal
    :open="Boolean(prompt)"
    :title="t('bootstrap.comp.maaRecoveryTitle')"
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
      <p>{{ t('bootstrap.comp.maaRecoveryMessage') }}</p>
      <a-descriptions bordered :column="1" size="small" class="recovery-details">
        <a-descriptions-item :label="t('bootstrap.comp.maaRecoveryManagedName')">
          {{ prompt.managedName || t('bootstrap.comp.maaRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.maaRecoveryInstallPath')">
          <span class="recovery-path">{{
            prompt.installPath || t('bootstrap.comp.maaRecoveryUnknown')
          }}</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.maaRecoveryCurrent')">
          {{ prompt.installedVersion || t('bootstrap.comp.maaRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.maaRecoveryTarget')">
          {{ prompt.targetVersion || t('bootstrap.comp.maaRecoveryUnknown') }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.maaRecoveryMarkerType')">
          {{
            prompt.hasResourceMarker
              ? t('bootstrap.comp.maaRecoveryResource')
              : t('bootstrap.comp.maaRecoverySoftware')
          }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('bootstrap.comp.maaRecoveryTakeover')">
          {{
            t(
              prompt.takeoverEnabled
                ? 'bootstrap.comp.maaRecoveryEnabled'
                : 'bootstrap.comp.maaRecoveryDisabled'
            )
          }}
        </a-descriptions-item>
      </a-descriptions>
      <a-alert
        class="recovery-warning"
        type="warning"
        show-icon
        :message="t('bootstrap.comp.maaRecoveryRisk')"
      />
      <a-checkbox
        v-if="prompt.canSkip"
        v-model:checked="acknowledged"
        :disabled="submitting"
        class="recovery-check"
      >
        {{ t('bootstrap.comp.maaRecoveryAcknowledgement') }}
      </a-checkbox>
      <a-alert
        v-if="sendFailed"
        class="recovery-error"
        type="error"
        show-icon
        :message="t('bootstrap.comp.maaRecoverySendFailed')"
      />
      <a-alert
        v-if="!prompt.canSkip || !prompt.canRetry"
        class="recovery-warning"
        type="info"
        show-icon
        :message="
          t(
            !prompt.canSkip
              ? 'bootstrap.comp.maaRecoveryResourceCannotSkip'
              : 'bootstrap.comp.maaRecoveryNoRetry'
          )
        "
      />
      <div class="recovery-actions">
        <a-button :disabled="submitting" @click="decide('stop')">
          {{ t('bootstrap.comp.maaRecoveryStop') }}
        </a-button>
        <a-button
          type="primary"
          :disabled="!prompt.canRetry || submitting"
          :loading="submitting"
          @click="decide('retry')"
        >
          {{ t('bootstrap.comp.maaRecoveryRetry') }}
        </a-button>
        <a-button
          v-if="prompt.canSkip"
          danger
          :disabled="!acknowledged || submitting"
          @click="decide('skip')"
        >
          {{ t('bootstrap.comp.maaRecoverySkip') }}
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
