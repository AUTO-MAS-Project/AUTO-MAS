<template>
  <div class="direct-control-section">
    <div class="section-header section-header--compact">
      <h3>{{ t('core.edit.directControl') }}</h3>
    </div>
    <!-- 直控跑什么、MAS 管什么由上方「直控」来源卡片说明，这里不再重复 -->
    <NoData
      v-if="availableEngines.length === 0"
      :description="t('core.edit.noSraMarch7thAssistant')"
    />
    <div v-else class="engine-grid">
      <div v-for="engine in availableEngines" :key="engine" class="engine-card">
        <div class="engine-card-header">
          <div>
            <div class="engine-name">{{ engineLabel(engine) }}</div>
            <!-- 云平台下 SRA 卡只在仍勾着时出现：说明它为何不能用，让用户关掉 -->
            <div class="engine-description">
              {{
                cloud && engine === 'SRA' ? t('core.edit.hsrCloudNoSra') : engineDescription(engine)
              }}
            </div>
          </div>
          <a-switch
            :checked="Boolean(control[engine])"
            :disabled="saving"
            :checked-children="t('core.edit.run')"
            :un-checked-children="t('core.edit.skip2')"
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
  /** 云·星穹铁道：只能用三月七直控，SRA 卡仅为关掉遗留勾选而显示。 */
  cloud?: boolean
}>()

const emit = defineEmits<{
  toggle: [engine: HSREngine, enabled: boolean]
}>()

const engineLabel = (engine: HSREngine) =>
  engine === 'M7A' ? t('core.edit.directEngineM7a') : t('core.edit.directEngineSra')
const engineDescription = (engine: HSREngine) =>
  engine === 'M7A' ? t('core.edit.directEngineDescM7a') : t('core.edit.directEngineDescSra')
</script>

<style scoped>
.direct-control-section {
  margin-bottom: 24px;
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
