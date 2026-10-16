<script setup lang="ts">
import { DeleteOutlined, UploadOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import { MASCOT_MAX_FPS, MASCOT_MIN_FPS, useMascotSettings } from '../useMascotSettings'

const { t } = useI18n()
const {
  modalContextHolder,
  selectedId,
  value,
  enabled,
  fpsMode,
  fps,
  available,
  options,
  busy,
  loading,
  selecting,
  toggling,
  saving,
  loadFailed,
  refresh,
  select,
  setEnabled,
  setFps,
  saveFps,
  setFpsMode,
  importMascot,
  removeMascot,
} = useMascotSettings()
</script>

<template>
  <div class="mascot-settings">
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
    <a-flex :gap="12" align="center" wrap="wrap">
      <a-space-compact class="mascot-source">
        <a-select
          class="mascot-select"
          :value="value"
          :options="options"
          :loading="loading || selecting"
          :disabled="busy || selecting || loadFailed"
          size="large"
          :aria-label="t('setting.basic.mascotSelect')"
          @change="select"
        />
        <a-button
          size="large"
          :loading="saving"
          :disabled="busy || selecting"
          @click="importMascot"
        >
          <template #icon><UploadOutlined /></template>{{ t('setting.basic.importMascot') }}
        </a-button>
        <a-button
          v-if="selectedId"
          size="large"
          danger
          :disabled="busy || selecting"
          :aria-label="t('setting.basic.removeMascot')"
          @click="removeMascot"
        >
          <template #icon><DeleteOutlined /></template>
        </a-button>
      </a-space-compact>
      <a-space :size="8">
        <span class="form-label">{{ t('setting.basic.desktopMascot') }}</span>
        <a-tooltip :title="t('setting.basic.desktopMascotTip')"
          ><QuestionCircleOutlined class="help-icon"
        /></a-tooltip>
        <a-switch
          :checked="enabled"
          :loading="toggling"
          :disabled="busy || toggling || !available || loadFailed"
          :aria-label="t('setting.basic.desktopMascot')"
          @change="(next: boolean) => setEnabled(next)"
        />
      </a-space>
      <a-space :size="8">
        <span class="form-label">{{ t('setting.basic.mascotFps') }}</span>
        <a-space-compact class="mascot-fps-controls">
          <a-select
            class="mascot-select"
            :value="fpsMode"
            :options="[
              { label: t('setting.basic.mascotFpsPackage'), value: 'package' },
              { label: t('setting.basic.mascotFpsCustom'), value: 'custom' },
            ]"
            :disabled="busy || loadFailed"
            size="large"
            :aria-label="t('setting.basic.mascotFps')"
            @change="setFpsMode"
          />
          <a-input-number
            v-if="fpsMode === 'custom'"
            class="mascot-fps-input"
            :value="fps"
            :min="MASCOT_MIN_FPS"
            :max="MASCOT_MAX_FPS"
            :precision="0"
            :step="1"
            :disabled="busy || loadFailed"
            size="large"
            addon-after="FPS"
            :aria-label="t('setting.basic.mascotFpsCustom')"
            @change="setFps"
            @blur="saveFps"
            @press-enter="saveFps"
          />
        </a-space-compact>
      </a-space>
    </a-flex>
    <a-flex vertical :gap="4" class="mascot-help">
      <a-typography-text type="secondary">{{
        t('setting.basic.mascotImportTip')
      }}</a-typography-text>
      <a-typography-text type="secondary">{{ t('setting.basic.mascotFpsTip') }}</a-typography-text>
      <a-typography-text v-if="!available && !loading" type="secondary">{{
        t('setting.basic.mascotUnavailable')
      }}</a-typography-text>
    </a-flex>
  </div>
</template>

<style scoped>
.mascot-select {
  flex: 1;
  min-width: 0;
}

.mascot-settings {
  margin-bottom: 16px;
}

.mascot-source {
  width: 340px;
  max-width: 100%;
}

.mascot-fps-controls {
  width: 250px;
}

.mascot-fps-input {
  width: 120px;
}

.mascot-help {
  margin-top: 8px;
}
</style>
