<script setup lang="ts">
import { DeleteOutlined, UploadOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
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
      <h3>{{ t('setting.basic.mascotSection') }}</h3>
    </div>
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
            <a-tooltip :title="t('setting.basic.mascotImportTip')">
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
              :aria-label="t('setting.basic.mascotSelect')"
              @change="select"
            />
            <a-button :loading="saving" :disabled="busy || selecting" @click="importMascot">
              <template #icon><UploadOutlined /></template>{{ t('setting.basic.importMascot') }}
            </a-button>
            <a-button
              v-if="selectedId"
              danger
              :disabled="busy || selecting"
              :aria-label="t('setting.basic.removeMascot')"
              @click="removeMascot"
            >
              <template #icon><DeleteOutlined /></template>{{ t('setting.basic.removeMascot') }}
            </a-button>
          </div>
        </div>
      </a-col>
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.basic.desktopMascot') }}</span>
            <a-tooltip>
              <template #title>
                <div>{{ t('setting.basic.desktopMascotTip') }}</div>
                <div v-if="!available && !loading && !loadFailed">
                  {{ t('setting.basic.mascotUnavailable') }}
                </div>
              </template>
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-select
            :value="enabled"
            :loading="toggling"
            :disabled="busy || toggling || !available || loadFailed"
            size="large"
            style="width: 100%"
            :aria-label="t('setting.basic.desktopMascot')"
            @change="(next: unknown) => setEnabled(next === true)"
          >
            <a-select-option :value="true">{{ t('common.on') }}</a-select-option>
            <a-select-option :value="false">{{ t('common.off') }}</a-select-option>
          </a-select>
        </div>
      </a-col>
    </a-row>
    <a-row :gutter="24">
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.basic.mascotFps') }}</span>
            <a-tooltip :title="t('setting.basic.mascotFpsTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-space-compact class="mascot-fps-controls" size="large">
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
            <a-select
              v-if="fpsMode === 'custom'"
              class="mascot-fps-select"
              :value="fps"
              :options="[8, 16, 24, 30, 60, 120].map(value => ({ label: `${value} FPS`, value }))"
              :disabled="busy || loadFailed"
              size="large"
              :aria-label="t('setting.basic.mascotFpsCustom')"
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
