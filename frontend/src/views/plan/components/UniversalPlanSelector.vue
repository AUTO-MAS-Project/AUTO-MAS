<template>
  <a-form-item :label="t('core.plan.type.universal')">
    <a-form-item-rest>
      <a-space direction="vertical" style="width: 100%">
        <a-switch
          :checked="enabled"
          :disabled="disabled || busy || Boolean(error)"
          :loading="busy"
          :aria-label="t('core.plan.universal.enable')"
          @change="toggle"
        />
        <template v-if="enabled">
          <a-alert type="info" show-icon :message="t('core.plan.universal.priority')" />
          <a-select
            style="width: 100%"
            :value="selected === 'Fixed' ? undefined : selected"
            :options="options"
            :placeholder="t('core.plan.universal.choosePlan')"
            :disabled="disabled || busy || Boolean(error)"
            @change="selectPlan"
          />
          <a-space>
            <a-button v-if="selected !== 'Fixed'" type="link" :disabled="busy" @click="editPlan">{{
              t('core.plan.universal.edit')
            }}</a-button>
            <a-button type="link" :disabled="busy" @click="router.push('/plans')">{{
              t('core.plan.universal.manage')
            }}</a-button>
          </a-space>
          <a-alert
            v-if="!options.length"
            type="info"
            show-icon
            :message="t('core.plan.universal.noPlans')"
          />
        </template>
        <a-alert v-if="error" type="error" :message="error" show-icon />
      </a-space>
    </a-form-item-rest>
  </a-form-item>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePlanApi } from '@/composables/usePlanApi'
import { useUserApi } from '@/composables/useUserApi'
import { PLAN_CONFIG_TYPES } from '@/utils/planTypeRegistry'
import type { GeneralUserConfig } from '@/api'
const { t } = useI18n()
const props = defineProps<{ scriptId: string; userId: string; disabled?: boolean }>()
const router = useRouter()
const { getPlans } = usePlanApi()
const { getUsers, updateUser } = useUserApi()
const busy = ref(false)
const enabled = ref(false)
const selected = ref('Fixed')
const error = ref('')
const options = ref<{ label: string; value: string }[]>([])
let revision = 0
watch(
  () => [props.scriptId, props.userId],
  async () => {
    const current = ++revision
    options.value = []
    selected.value = 'Fixed'
    enabled.value = false
    busy.value = true
    error.value = ''
    try {
      const [all, users] = await Promise.all([getPlans(), getUsers(props.scriptId, props.userId)])
      if (current !== revision) return
      if (all.code !== 200 || users?.code !== 200)
        throw new Error(t('core.plan.universal.readFailed'))
      options.value = all.index.flatMap(item => {
        const info = all.data[item.uid]?.Info
        return item.type === PLAN_CONFIG_TYPES.UNIVERSAL &&
          info &&
          'ScriptId' in info &&
          info.ScriptId === props.scriptId
          ? [{ label: info.Name ?? t('core.plan.type.universal'), value: item.uid }]
          : []
      })
      selected.value = (users.data[props.userId] as GeneralUserConfig)?.Info?.PlanMode ?? 'Fixed'
      enabled.value = selected.value !== 'Fixed'
    } catch (reason) {
      if (current === revision) error.value = String(reason)
    } finally {
      if (current === revision) busy.value = false
    }
  },
  { immediate: true }
)
async function selectPlan(value: unknown) {
  if (typeof value !== 'string') return
  busy.value = true
  try {
    if (await updateUser(props.scriptId, props.userId, { Info: { PlanMode: value } })) {
      selected.value = value
      enabled.value = value !== 'Fixed'
    }
  } finally {
    busy.value = false
  }
}
async function toggle(value: boolean | string | number) {
  if (value) {
    enabled.value = true
    if (selected.value === 'Fixed' && options.value.length) await selectPlan(options.value[0].value)
  } else {
    await selectPlan('Fixed')
  }
}
function editPlan() {
  void router.push({ path: '/plans', query: { planId: selected.value } })
}
</script>
