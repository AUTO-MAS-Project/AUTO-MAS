<template>
  <a-card class="config-card">
    <a-form :model="task" :disabled="disabled" layout="vertical" class="config-form">
      <div class="form-section">
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

        <template v-if="quickConfig">
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item :label="t('core.edit.spendSanityFarm')">
                <a-select
                  v-model:value="task.WhichToFarm"
                  size="large"
                  :options="farmOptions"
                  @change="emit('save')"
                />
              </a-form-item>
            </a-col>
            <a-col v-if="task.WhichToFarm === 'Tacet Suppression'" :span="12">
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
            <a-col v-else-if="task.WhichToFarm === 'Forgery Challenge'" :span="12">
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
            <a-col v-else :span="12">
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
            <a-switch v-model:checked="task.FarmNightmareNestForDailyEcho" @change="emit('save')" />
          </a-form-item>

          <a-form-item :label="t('core.edit.extraTasksThatRun')">
            <a-checkbox-group
              v-model:value="task.AdditionalTasks"
              :options="additionalTaskOptions"
              @change="emit('save')"
            />
          </a-form-item>
        </template>
      </div>
    </a-form>
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { farmOptions, materialOptions, additionalTaskOptions } from '@/utils/okwwTaskOptions'
import OkwwArgumentsConfig from './OkwwArgumentsConfig.vue'
import type { OkwwTaskForm } from './okwwTaskConfig'

const task = defineModel<OkwwTaskForm>({ required: true })
defineProps<{
  quickConfig: boolean
  disabled: boolean
  scriptId: string
  saveTask: () => Promise<boolean>
}>()
const emit = defineEmits<{ save: [] }>()
const { t } = useI18n()
</script>
