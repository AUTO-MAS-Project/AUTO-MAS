<template>
  <a-card class="config-card">
    <a-form :model="task" :disabled="disabled" layout="vertical" class="config-form">
      <div class="form-section">
        <a-row :gutter="24">
          <a-col :span="24">
            <a-form-item>
              <template #label>
                <FieldLabelWithHint
                  :text="t('core.edit.currentLaunchArguments')"
                  :hint="t('core.edit.argumentsGeneratedFromTask')"
                  variant="form"
                />
              </template>
              <a-input :value="currentStartupArguments" size="large" readonly />
            </a-form-item>
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
import type { OkwwUserConfig } from '@/api'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'

type TaskForm = {
  [K in keyof NonNullable<OkwwUserConfig['Task']>]-?: NonNullable<
    NonNullable<OkwwUserConfig['Task']>[K]
  >
}
const task = defineModel<TaskForm>({ required: true })
defineProps<{ quickConfig: boolean; disabled: boolean }>()
const emit = defineEmits<{ save: []; 'task-change': [value: TaskForm['TaskName']] }>()
const { t } = useI18n()
const currentStartupArguments = '-t 1 -e'

const farmOptions = [
  { label: '无音区', value: 'Tacet Suppression' },
  { label: '凝素领域', value: 'Forgery Challenge' },
  { label: '模拟领域', value: 'Simulation Challenge' },
]

const materialOptions = [
  { label: '共鸣者经验', value: 'Resonator EXP' },
  { label: '武器经验', value: 'Weapon EXP' },
  { label: '贝币', value: 'Shell Credit' },
]

const additionalTaskOptions = [
  { label: '检查每周乐园', value: 'Check Weekly Garden' },
  { label: '自动刷所有梦魇巢穴', value: 'Auto Farm all Nightmare Nest' },
  { label: '已弃置声骸超过 1000 时融合', value: 'Merge Echo If discarded > 1000' },
  { label: '传送并刷取 4C 声骸', value: 'Teleport and Farm 4C Echo' },
]
</script>
