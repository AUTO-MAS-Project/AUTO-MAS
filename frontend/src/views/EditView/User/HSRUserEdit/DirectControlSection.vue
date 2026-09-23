<template>
  <div class="direct-control-section">
    <div class="section-header">
      <h3>{{ t('edit.scriptDirectControl') }}</h3>
    </div>
    <!-- 直控区块唯一的一条提示：说明直控跑什么、MAS 管什么、哪些字段此时不生效 -->
    <a-alert type="info" show-icon :message="t('edit.hsrDirectControlHint')" class="direct-alert" />

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
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { HSREngine } from '@/composables/useHSRPluginApi'
import type { HSRUserConfigData } from './types'

const { t } = useI18n()

defineProps<{
  availableEngines: HSREngine[]
  control: NonNullable<HSRUserConfigData['Control']>
  saving: boolean
}>()

const emit = defineEmits<{
  toggle: [engine: HSREngine, enabled: boolean]
}>()

const engineLabel = (engine: HSREngine) =>
  engine === 'M7A' ? t('edit.directEngineM7a') : t('edit.directEngineSra')
const engineDescription = (engine: HSREngine) =>
  engine === 'M7A' ? t('edit.directEngineDescM7a') : t('edit.directEngineDescSra')
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

.engine-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.engine-name {
  font-size: 17px;
  font-weight: 700;
}

.engine-description {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}
</style>
