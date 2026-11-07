<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { QueueConfig_Info, QueueUpdateIn } from '@/api'
import { PowerSignal } from '@/api'
import { queueApi } from '@/composables/useQueueApi'
import SettingToggleButton from '@/components/SettingToggleButton.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'

const props = defineProps<{
  queueId: string
  info?: QueueConfig_Info | null
}>()
const emit = defineEmits<{ refresh: [] }>()
const { t } = useI18n()
type QueuePatch = QueueUpdateIn['data']
type StartupMode = NonNullable<NonNullable<QueuePatch['Info']>['StartUpMode']>
const startup = ref<StartupMode>('Never')
const timed = ref(false)
const cyclic = ref(false)
const after = ref(PowerSignal.NO_ACTION)
const delay = ref<number | null>(1)
const saving = ref(false)

// 完成后操作选项。label 随语言变，必须是 computed
const afterOptions = computed(() => [
  { label: t('core.queue.action.NoAction'), value: PowerSignal.NO_ACTION },
  { label: t('core.queue.action.Shutdown'), value: PowerSignal.SHUTDOWN },
  { label: t('core.queue.action.ShutdownForce'), value: PowerSignal.SHUTDOWN_FORCE },
  { label: t('core.queue.action.Reboot'), value: PowerSignal.REBOOT },
  { label: t('core.queue.action.Hibernate'), value: PowerSignal.HIBERNATE },
  { label: t('core.queue.action.Sleep'), value: PowerSignal.SLEEP },
  { label: t('core.queue.action.KillSelf'), value: PowerSignal.KILL_SELF },
  { label: t('core.queue.action.RestartSelf'), value: PowerSignal.RESTART_SELF },
  { label: t('core.queue.action.Logoff'), value: PowerSignal.LOGOFF },
])

watch(
  () => props.info,
  () => {
    startup.value = props.info?.StartUpMode ?? 'Never'
    timed.value = props.info?.TimeEnabled ?? false
    cyclic.value = props.info?.CycleEnabled ?? false
    after.value = props.info?.AfterAccomplish ?? PowerSignal.NO_ACTION
    delay.value = props.info?.AfterAccomplishDelay ?? 1
  },
  { immediate: true }
)

async function save(data: QueuePatch) {
  saving.value = true
  try {
    const response = await queueApi.updateQueue({ queueId: props.queueId, data })
    if (response.code !== 200) throw new Error(response.message)
  } catch (error) {
    message.error(error instanceof Error ? error.message : String(error))
  } finally {
    saving.value = false
    emit('refresh')
  }
}

function saveDelay() {
  const value = delay.value ?? 1
  delay.value = value
  if (value !== (props.info?.AfterAccomplishDelay ?? 1))
    void save({ Info: { AfterAccomplishDelay: value } })
}
</script>

<template>
  <a-form layout="vertical" class="queue-trigger-settings" :disabled="saving">
    <a-row :gutter="[24, 0]">
      <a-col :xs="24" :sm="8" :xl="5">
        <a-form-item :label="t('core.queue.runOnStart')">
          <a-select
            v-model:value="startup"
            size="large"
            @change="save({ Info: { StartUpMode: startup } })"
          >
            <a-select-option value="Never">{{ t('core.queue.never') }}</a-select-option>
            <a-select-option value="Always">{{ t('core.queue.always') }}</a-select-option>
            <a-select-option value="DailyFirst">{{ t('core.queue.dailyFirst') }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :xs="24" :sm="8" :xl="5">
        <a-form-item :label="t('core.queue.scheduled')">
          <SettingToggleButton
            v-model="timed"
            :loading="saving"
            style="width: 100%"
            @change="value => save({ Info: { TimeEnabled: value } })"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :sm="8" :xl="5">
        <a-form-item :label="t('core.queue.triggers.cycleEnabled')">
          <SettingToggleButton
            v-model="cyclic"
            :loading="saving"
            style="width: 100%"
            @change="value => save({ Info: { CycleEnabled: value } })"
          />
        </a-form-item>
      </a-col>
      <!-- 两项始终共用原来的 9 列；隐藏延迟时由完成后操作占满。 -->
      <a-col :xs="24" :sm="24" :xl="9" class="after-action-group">
        <a-row :gutter="[16, 0]">
          <a-col :span="after === PowerSignal.NO_ACTION ? 24 : 14">
            <a-form-item>
              <template #label>
                <FieldLabelWithHint
                  variant="form"
                  :text="t('core.queue.afterDone')"
                  :hint="t('core.queue.afterDoneTip')"
                />
              </template>
              <a-select
                v-model:value="after"
                :options="afterOptions"
                :aria-label="t('core.queue.afterDone')"
                size="large"
                class="after-action-select"
                @change="save({ Info: { AfterAccomplish: after } })"
              />
            </a-form-item>
          </a-col>
          <a-col v-if="after !== PowerSignal.NO_ACTION" :span="10">
            <a-form-item>
              <template #label>
                <FieldLabelWithHint
                  variant="form"
                  :text="t('core.queue.afterDoneDelay')"
                  :hint="t('core.queue.afterDoneDelayTip')"
                />
              </template>
              <a-input-number
                v-model:value="delay"
                size="large"
                :min="1"
                :max="1440"
                :precision="0"
                :disabled="saving"
                :addon-after="t('core.queue.afterDoneDelayUnit')"
                :aria-label="t('core.queue.afterDoneDelay')"
                class="after-action-delay"
                @blur="saveDelay"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-col>
    </a-row>
  </a-form>
</template>

<style scoped>
.queue-trigger-settings :deep(.ant-form-item-label > label) {
  font-weight: 600;
}

.after-action-select,
.after-action-delay {
  width: 100%;
}
</style>
