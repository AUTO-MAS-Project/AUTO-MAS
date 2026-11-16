<template>
  <a-card class="config-card">
    <a-form :model="task" :disabled="disabled" layout="vertical" class="config-form">
      <div class="form-section">
        <a-tabs :tab-position="screens.md ? 'left' : 'top'" default-active-key="daily">
          <a-tab-pane key="daily" :tab="t('core.edit.okwwDailyTab')">
            <OkwwNativeTaskConfig
              :script-id="scriptId"
              :user-id="userId"
              kind="daily"
              :snapshot="task.DailyConfig"
              @busy="setBusy('daily', $event)"
              :disabled="disabled"
              :overlay-enabled="overlayEnabled"
              @saved="emit('refresh')"
            />
          </a-tab-pane>
          <a-tab-pane key="echo" :tab="t('core.edit.okwwEchoConfigTitle')">
            <OkwwNativeTaskConfig
              :script-id="scriptId"
              :user-id="userId"
              kind="echo"
              :snapshot="task.FarmEchoConfig"
              @busy="setBusy('echo', $event)"
              :disabled="disabled"
              :overlay-enabled="overlayEnabled"
              @saved="emit('refresh')"
            />
          </a-tab-pane>
          <a-tab-pane v-for="panel in advancedPanels" :key="panel.kind" :tab="t(panel.label)">
            <OkwwNativeTaskConfig
              :script-id="scriptId"
              :user-id="userId"
              :kind="panel.kind"
              :snapshot="task.NativeConfigs[panel.filename] ?? emptyConfig"
              :disabled="disabled"
              :overlay-enabled="overlayEnabled"
              @saved="emit('refresh')"
              @busy="setBusy(panel.kind, $event)"
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
import { reactive } from 'vue'
import { Grid } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import OkwwNativeTaskConfig from './OkwwNativeTaskConfig.vue'
import OkwwArgumentsConfig from './OkwwArgumentsConfig.vue'
import type { OkwwPanelKind } from '@/types/nativeConfig'
import type { OkwwTaskForm } from './okwwTaskConfig'

const task = defineModel<OkwwTaskForm>({ required: true })
defineProps<{
  overlayEnabled: boolean
  disabled: boolean
  userId: string
  scriptId: string
  saveTask: () => Promise<boolean>
}>()
const emit = defineEmits<{ save: []; refresh: []; busy: [value: boolean] }>()
const { t } = useI18n()
const screens = Grid.useBreakpoint()
const emptyConfig = {}
const advancedPanels: { kind: OkwwPanelKind; filename: string; label: string }[] = [
  { kind: 'nightmare', filename: 'NightmareNestTask.json', label: 'core.edit.okwwPanelNightmare' },
  { kind: 'combat', filename: 'AutoCombatTask.json', label: 'core.edit.okwwPanelCombat' },
  { kind: 'character', filename: 'Character Config.json', label: 'core.edit.okwwPanelCharacter' },
  { kind: 'monthly', filename: 'Monthly Card Config.json', label: 'core.edit.okwwPanelMonthly' },
]
const busy = reactive<Partial<Record<OkwwPanelKind, boolean>>>({})
function setBusy(kind: OkwwPanelKind, value: boolean) {
  busy[kind] = value
  emit('busy', Object.values(busy).some(Boolean))
}
</script>
