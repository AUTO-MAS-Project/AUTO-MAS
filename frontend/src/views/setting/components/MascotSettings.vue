<script setup lang="ts">
import { DeleteOutlined, UploadOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import { useI18n } from 'vue-i18n'
import { useMascotSettings } from '../useMascotSettings'

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

const handleFpsChange = (next: SelectValue): void => {
  if (typeof next !== 'number') return
  setFps(next)
  void saveFps()
}
</script>

<template>
  <div class="form-section mascot-settings">
    <component :is="modalContextHolder" />
    <div class="section-header">
      <h3>{{ t('core.setting.basic.mascotSection') }}</h3>
    </div>
    <a-alert
      v-if="loadFailed"
      type="error"
      :message="t('core.setting.basic.mascotLoadFailed')"
      show-icon
    >
      <template #action
        ><a-button size="small" @click="refresh">{{
          t('core.setting.basic.mascotRetry')
        }}</a-button></template
      >
    </a-alert>
    <a-row :gutter="24">
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('core.setting.basic.mascotSelect') }}</span>
            <a-tooltip :title="t('core.setting.basic.mascotImportTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <div class="mascot-source">
            <a-select
              class="mascot-source-select"
              :value="value"
              :options="options"
              :loading="loading || selecting"
              :disabled="busy || selecting || loadFailed"
              size="large"
              :aria-label="t('core.setting.basic.mascotSelect')"
              @change="select"
            />
            <a-button :loading="saving" :disabled="busy || selecting" @click="importMascot">
              <template #icon><UploadOutlined /></template
              >{{ t('core.setting.basic.importMascot') }}
            </a-button>
            <a-button
              v-if="selectedId"
              danger
              :disabled="busy || selecting"
              :aria-label="t('core.setting.basic.removeMascot')"
              @click="removeMascot"
            >
              <template #icon><DeleteOutlined /></template
              >{{ t('core.setting.basic.removeMascot') }}
            </a-button>
          </div>
        </div>
      </a-col>
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <a-checkbox
              :checked="enabled"
              :aria-busy="toggling"
              :disabled="busy || toggling || !available || loadFailed"
              @change="(event: CheckboxChangeEvent) => setEnabled(event.target.checked)"
            >
              {{ t('core.setting.basic.desktopMascot') }}
            </a-checkbox>
            <a-tooltip>
              <template #title>
                <div>{{ t('core.setting.basic.desktopMascotTip') }}</div>
                <div v-if="!available && !loading && !loadFailed">
                  {{ t('core.setting.basic.mascotUnavailable') }}
                </div>
              </template>
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
        </div>
      </a-col>
    </a-row>
    <a-row :gutter="24">
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('core.setting.basic.mascotFps') }}</span>
            <a-tooltip :title="t('core.setting.basic.mascotFpsTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-space-compact class="mascot-fps-controls" size="large">
            <a-select
              class="mascot-select"
              :value="fpsMode"
              :options="[
                { label: t('core.setting.basic.mascotFpsPackage'), value: 'package' },
                { label: t('core.setting.basic.mascotFpsCustom'), value: 'custom' },
              ]"
              :disabled="busy || loadFailed"
              size="large"
              :aria-label="t('core.setting.basic.mascotFps')"
              @change="setFpsMode"
            />
            <a-select
              v-if="fpsMode === 'custom'"
              class="mascot-fps-select"
              :value="fps"
              :options="[8, 16, 24, 30, 60, 120].map(value => ({ label: `${value} FPS`, value }))"
              :disabled="busy || loadFailed"
              size="large"
              :aria-label="t('core.setting.basic.mascotFpsCustom')"
              @change="handleFpsChange"
            />
          </a-space-compact>
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

.mascot-source {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.mascot-source-select {
  flex: 1 1 144px;
  min-width: 144px;
}

.mascot-fps-controls {
  width: 100%;
}

.mascot-fps-select {
  width: 132px;
}

@media (max-width: 1440px) {
  .mascot-source-select {
    flex-basis: 100%;
  }
}
</style>
