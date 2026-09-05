<template>
  <div class="direct-control-section">
    <div class="section-header">
      <h3>{{ t('edit.scriptDirectControl') }}</h3>
    </div>
    <a-alert type="info" show-icon :message="t('edit.finishNativeSetupSra')" class="direct-alert" />

    <a-empty v-if="availableEngines.length === 0" :description="t('edit.noSraMarch7thAssistant')" />
    <div v-else class="engine-grid">
      <div v-for="engine in availableEngines" :key="engine" class="engine-card">
        <div class="engine-card-header">
          <div>
            <div class="engine-name">{{ engineLabel(engine) }}</div>
            <div class="engine-description">{{ engineDescription(engine) }}</div>
          </div>
          <a-switch
            :checked="Boolean(control[engine])"
            :disabled="saving"
            :checked-children="t('edit.run')"
            :un-checked-children="t('edit.skip2')"
            @change="emit('toggle', engine, Boolean($event))"
          />
        </div>

        <div class="import-state" :class="{ 'import-state-ready': importedAt(engine) }">
          <CheckCircleOutlined v-if="importedAt(engine)" />
          <InfoCircleOutlined v-else />
          <div>
            <div>{{ importedAt(engine) ? '已导入用户快照' : '尚未导入用户快照' }}</div>
            <div v-if="importedAt(engine)" class="import-meta">
              {{ source(engine) }} · {{ importedAt(engine) }}
            </div>
          </div>
        </div>

        <a-space wrap>
          <a-button
            type="primary"
            :disabled="saving"
            :loading="importingEngine === engine"
            @click="emit('importConfig', engine)"
          >
            {{ t('edit.importFromSourceConfiguration') }}
          </a-button>
        </a-space>
      </div>
    </div>

    <a-alert
      v-if="selectedEngines.length === 0"
      type="warning"
      show-icon
      :message="t('edit.enableAtLeastOne')"
      class="direct-alert bottom-alert"
    />
    <a-alert
      v-else-if="selectedEngines.some(engine => !importedAt(engine))"
      type="warning"
      show-icon
      :message="t('edit.enabledScriptNeedsUser')"
      class="direct-alert bottom-alert"
    />

    <div class="managed-mask-preview">
      <div class="mask-copy">
        <LockOutlined />
        <div>
          <strong>{{ t('edit.masManagedConfigurationOff') }}</strong>
          <span>{{ t('edit.taskSwitchesAccountsSanity') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { CheckCircleOutlined, InfoCircleOutlined, LockOutlined } from '@ant-design/icons-vue'
import type { HSREngine } from '@/composables/useHSRPluginApi'
import type { HSRUserConfigData } from './types'

const { t } = useI18n()

const props = defineProps<{
  availableEngines: HSREngine[]
  control: NonNullable<HSRUserConfigData['Control']>
  direct: NonNullable<HSRUserConfigData['Direct']>
  saving: boolean
  importingEngine: HSREngine | null
}>()

const emit = defineEmits<{
  toggle: [engine: HSREngine, enabled: boolean]
  importConfig: [engine: HSREngine]
}>()

const selectedEngines = computed(() =>
  props.availableEngines.filter(engine => Boolean(props.control[engine]))
)

const engineLabel = (engine: HSREngine) => (engine === 'M7A' ? '三月七助手 CLI' : 'SRA CLI')
const engineDescription = (engine: HSREngine) =>
  engine === 'M7A' ? '执行导入的 config.yaml 快照' : '执行导入的 SRA JSON 配置快照'
const importedAt = (engine: HSREngine) =>
  String(props.direct[`${engine}ImportedAt` as keyof HSRUserConfigData['Direct']] || '')
const source = (engine: HSREngine) =>
  String(props.direct[`${engine}Source` as keyof HSRUserConfigData['Direct']] || '')
</script>

<style scoped>
.direct-control-section {
  margin-bottom: 24px;
}

.section-header {
  margin-bottom: 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  gap: 10px;
  font-size: 18px;
}

.section-header h3::before {
  height: 20px;
  background: var(--ant-color-primary);
}

.direct-alert {
  margin-bottom: 16px;
}

.engine-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.engine-card {
  padding: 20px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  background: var(--ant-color-bg-container);
}

.engine-card-header,
.import-state,
.mask-copy {
  display: flex;
  align-items: center;
}

.engine-card-header {
  justify-content: space-between;
  gap: 16px;
}

.engine-name {
  font-size: 17px;
  font-weight: 700;
}

.engine-description,
.import-meta,
.mask-copy span {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.import-state {
  gap: 10px;
  margin: 16px 0;
  padding: 12px;
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-warning);
}

.import-state-ready {
  color: var(--ant-color-success);
}

.import-meta {
  overflow: hidden;
  max-width: 520px;
  margin-top: 3px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bottom-alert {
  margin-top: 16px;
}

.managed-mask-preview {
  position: relative;
  min-height: 120px;
  margin-top: 20px;
  overflow: hidden;
  border: 1px dashed var(--ant-color-border);
  border-radius: 10px;
  background:
    linear-gradient(rgb(255 255 255 / 72%), rgb(255 255 255 / 72%)),
    repeating-linear-gradient(
      135deg,
      var(--ant-color-fill-quaternary) 0 14px,
      transparent 14px 28px
    );
}

.mask-copy {
  position: absolute;
  inset: 0;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  text-align: left;
}

.mask-copy strong,
.mask-copy span {
  display: block;
}
</style>
