<script setup lang="ts">
import { computed } from 'vue'
import {
  DeleteOutlined,
  QuestionCircleOutlined,
  SmileOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import { useI18n } from 'vue-i18n'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
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

const fpsModeOptions = computed(() => [
  { label: t('core.setting.basic.mascotFpsPackage'), value: 'package' },
  { label: t('core.setting.basic.mascotFpsCustom'), value: 'custom' },
])
const fpsOptions = [8, 16, 24, 30, 60, 120].map(value => ({ label: `${value} FPS`, value }))
</script>

<template>
  <SectionCard :title="t('core.setting.basic.mascotSection')" :icon="SmileOutlined">
    <component :is="modalContextHolder" />
    <a-alert
      v-if="loadFailed"
      class="mascot-load-alert"
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

    <SettingRow
      :label="t('core.setting.basic.mascotSelect')"
      :hint="t('core.setting.basic.mascotImportTip')"
    >
      <div class="mascot-source">
        <a-select
          class="mascot-source-select"
          :value="value"
          :options="options"
          :loading="loading || selecting"
          :disabled="busy || selecting || loadFailed"
          :aria-label="t('core.setting.basic.mascotSelect')"
          @change="select"
        />
        <a-button :loading="saving" :disabled="busy || selecting" @click="importMascot">
          <template #icon><UploadOutlined /></template>
          {{ t('core.setting.basic.importMascot') }}
        </a-button>
        <a-button
          v-if="selectedId"
          danger
          :disabled="busy || selecting"
          :aria-label="t('core.setting.basic.removeMascot')"
          @click="removeMascot"
        >
          <template #icon><DeleteOutlined /></template>
          {{ t('core.setting.basic.removeMascot') }}
        </a-button>
      </div>
    </SettingRow>

    <SettingRow :label="t('core.setting.basic.desktopMascot')">
      <template #label>
        <a-tooltip>
          <template #title>
            <div>{{ t('core.setting.basic.desktopMascotTip') }}</div>
            <div v-if="!available && !loading && !loadFailed">
              {{ t('core.setting.basic.mascotUnavailable') }}
            </div>
          </template>
          <span class="row-label" tabindex="0">
            {{ t('core.setting.basic.desktopMascot') }}
            <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
          </span>
        </a-tooltip>
      </template>
      <a-switch
        :checked="enabled"
        :loading="toggling"
        :aria-busy="toggling"
        :disabled="busy || toggling || !available || loadFailed"
        :aria-label="t('core.setting.basic.desktopMascot')"
        @change="(checked: boolean | string | number) => setEnabled(!!checked)"
      />
    </SettingRow>

    <SettingRow
      :label="t('core.setting.basic.mascotFps')"
      :hint="t('core.setting.basic.mascotFpsTip')"
    >
      <div class="mascot-fps-controls">
        <a-segmented
          :value="fpsMode"
          :options="fpsModeOptions"
          :disabled="busy || loadFailed"
          :aria-label="t('core.setting.basic.mascotFps')"
          @change="(next: any) => setFpsMode(next)"
        />
        <a-select
          v-if="fpsMode === 'custom'"
          class="mascot-fps-select"
          :value="fps"
          :options="fpsOptions"
          :disabled="busy || loadFailed"
          :aria-label="t('core.setting.basic.mascotFpsCustom')"
          @change="handleFpsChange"
        />
      </div>
    </SettingRow>
  </SectionCard>
</template>

<style scoped>
.mascot-load-alert {
  margin: 0 0 4px;
}

.mascot-source {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-width: 0;
}

.mascot-source-select {
  width: 240px;
}

.mascot-fps-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.mascot-fps-select {
  width: 112px;
}

.row-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  cursor: help;
}

.row-label:focus-visible {
  border-radius: 3px;
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}
</style>
