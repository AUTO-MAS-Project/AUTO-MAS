<script setup lang="ts">
import { DeleteOutlined, UploadOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import { useMascotSettings } from '../useMascotSettings'

const { t } = useI18n()
const {
  modalContextHolder,
  selectedId,
  value,
  enabled,
  available,
  options,
  busy,
  loading,
  saving,
  loadFailed,
  refresh,
  select,
  setEnabled,
  importMascot,
  removeMascot,
} = useMascotSettings()
</script>

<template>
  <div>
    <component :is="modalContextHolder" />
    <a-alert
      v-if="loadFailed"
      type="error"
      :message="t('setting.basic.mascotLoadFailed')"
      show-icon
    >
      <template #action
        ><a-button size="small" @click="refresh">{{
          t('setting.basic.mascotRetry')
        }}</a-button></template
      >
    </a-alert>
    <a-row :gutter="24">
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.basic.mascotSelect') }}</span>
          </div>
          <a-space-compact block>
            <a-select
              class="mascot-select"
              :value="value"
              :options="options"
              :loading="loading"
              :disabled="busy || loadFailed"
              size="large"
              :aria-label="t('setting.basic.mascotSelect')"
              @change="select"
            />
            <a-button size="large" :loading="saving" :disabled="busy" @click="importMascot">
              <template #icon><UploadOutlined /></template>{{ t('setting.basic.importMascot') }}
            </a-button>
            <a-button
              v-if="selectedId"
              size="large"
              danger
              :disabled="busy"
              :aria-label="t('setting.basic.removeMascot')"
              @click="removeMascot"
            >
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </a-space-compact>
          <a-typography-text type="secondary">{{
            t('setting.basic.mascotImportTip')
          }}</a-typography-text>
          <a-typography-text v-if="!available && !loading" type="secondary">{{
            t('setting.basic.mascotUnavailable')
          }}</a-typography-text>
        </div>
      </a-col>
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.basic.desktopMascot') }}</span>
            <a-tooltip :title="t('setting.basic.desktopMascotTip')"
              ><QuestionCircleOutlined class="help-icon"
            /></a-tooltip>
          </div>
          <a-switch
            class="mascot-switch"
            :checked="enabled"
            :loading="saving"
            :disabled="busy || !available || loadFailed"
            :aria-label="t('setting.basic.desktopMascot')"
            @change="(next: boolean) => setEnabled(next)"
          />
        </div>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped>
.mascot-select {
  flex: 1;
  min-width: 0;
}

.mascot-switch {
  align-self: flex-start;
}
</style>
