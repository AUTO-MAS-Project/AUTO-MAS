<template>
  <a-card class="config-card">
    <a-form :model="task" :disabled="disabled" layout="vertical" class="config-form">
      <div class="form-section">
        <a-tabs :tab-position="screens.md ? 'left' : 'top'" default-active-key="daily">
          <a-tab-pane key="daily" :tab="t('core.edit.okwwDailyTab')">
            <template v-if="quickConfig">
              <a-row :gutter="24">
                <a-col :xs="24" :md="12">
                  <a-form-item :label="t('core.edit.spendSanityFarm')">
                    <a-select
                      v-model:value="task.WhichToFarm"
                      size="large"
                      :options="farmOptions"
                      @change="emit('save')"
                    />
                  </a-form-item>
                </a-col>
                <a-col v-if="task.WhichToFarm === 'Tacet Suppression'" :xs="24" :md="12">
                  <a-form-item :label="t('core.edit.sonanceCasketNumberF2')">
                    <a-input-number
                      v-model:value="task.WhichTacetSuppressionToFarm"
                      :min="1"
                      :max="99"
                      style="width: 100%"
                      size="large"
                      @blur="emit('save')"
                    />
                  </a-form-item>
                </a-col>
                <a-col v-else-if="task.WhichToFarm === 'Forgery Challenge'" :xs="24" :md="12">
                  <a-form-item :label="t('core.edit.echoDomainNumberF2')">
                    <a-input-number
                      v-model:value="task.WhichForgeryChallengeToFarm"
                      :min="1"
                      :max="99"
                      style="width: 100%"
                      size="large"
                      @blur="emit('save')"
                    />
                  </a-form-item>
                </a-col>
                <a-col v-else :xs="24" :md="12">
                  <a-form-item :label="t('core.edit.simulatedUniverseMaterials')">
                    <a-select
                      v-model:value="task.MaterialSelection"
                      size="large"
                      :options="materialOptions"
                      @change="emit('save')"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-form-item :label="t('core.edit.useNightmareNestDaily')">
                <a-switch
                  v-model:checked="task.FarmNightmareNestForDailyEcho"
                  @change="emit('save')"
                />
              </a-form-item>

              <a-form-item :label="t('core.edit.extraTasksThatRun')">
                <a-checkbox-group
                  v-model:value="task.AdditionalTasks"
                  class="additional-tasks"
                  :options="additionalTaskOptions"
                  @change="emit('save')"
                />
              </a-form-item>
            </template>
            <a-empty v-if="!quickConfig" :description="t('core.edit.okwwDailyManagedHint')" />
          </a-tab-pane>
          <a-tab-pane key="echo" :tab="t('core.edit.okwwEchoConfigTitle')">
            <OkwwEchoConfig
              v-model="task.FarmEchoConfig"
              :disabled="disabled"
              :overlay-enabled="overlayEnabled"
              @save="emit('save')"
              @configure="emit('configure')"
            />
          </a-tab-pane>
          <a-tab-pane key="arguments" :tab="t('core.edit.okwwArgumentsTab')" force-render>
            <a-row :gutter="24">
              <a-col :span="24">
                <OkwwArgumentsConfig
                  :script-id="scriptId"
                  :save="saveTask"
                  v-model="task"
                  @save="emit('save')"
                />
              </a-col>
            </a-row>
          </a-tab-pane>
        </a-tabs>
      </div>
    </a-form>
  </a-card>
</template>

<script setup lang="ts">
import { Grid } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { farmOptions, materialOptions, additionalTaskOptions } from '@/utils/okwwTaskOptions'
import OkwwEchoConfig from './OkwwEchoConfig.vue'
import OkwwArgumentsConfig from './OkwwArgumentsConfig.vue'
import type { OkwwTaskForm } from './okwwTaskConfig'

const task = defineModel<OkwwTaskForm>({ required: true })
defineProps<{
  overlayEnabled: boolean
  quickConfig: boolean
  disabled: boolean
  scriptId: string
  saveTask: () => Promise<boolean>
}>()
const emit = defineEmits<{ save: []; configure: [] }>()
const { t } = useI18n()
const screens = Grid.useBreakpoint()
</script>

<style scoped>
.additional-tasks {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 24px;
}
.additional-tasks :deep(.ant-checkbox-wrapper) {
  margin-inline-start: 0;
}
@media (max-width: 768px) {
  .additional-tasks {
    grid-template-columns: 1fr;
  }
}
</style>
