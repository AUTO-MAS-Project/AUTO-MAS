<template>
  <a-row :gutter="24">
    <a-col :xs="24" :md="12">
      <a-form-item>
        <template #label>
          <FieldLabelWithHint
            :text="
              t(
                planType === PLAN_CONFIG_TYPES.OKWW
                  ? 'core.plan.type.okww'
                  : planType === PLAN_CONFIG_TYPES.OKNTE
                    ? 'core.plan.type.oknte'
                    : 'core.plan.type.universal'
              )
            "
            :hint="t('core.plan.universal.priority')"
            variant="form"
          />
        </template>
        <a-select
          class="universal-plan-select"
          size="large"
          :value="selected"
          :options="options"
          :loading="busy"
          :disabled="disabled || busy || Boolean(error)"
          @change="selectPlan"
        />
      </a-form-item>
    </a-col>
    <a-col v-if="enabled || !planOptions.length" :xs="24" :md="12" class="plans-link-col">
      <a-button type="link" class="plans-button" :disabled="busy" @click="goToPlans">
        <template #icon><CalendarOutlined /></template>
        {{ t('core.edit.goPlan') }}
      </a-button>
    </a-col>
  </a-row>
  <a-alert v-if="error" type="error" show-icon :message="error" />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CalendarOutlined } from '@ant-design/icons-vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { navigateTo } from '@/router'
import { usePlanApi } from '@/composables/usePlanApi'
import { useUserApi } from '@/composables/useUserApi'
import { PLAN_CONFIG_TYPES } from '@/utils/planTypeRegistry'

const { t } = useI18n()
const props = defineProps<{
  scriptId: string
  userId: string
  planMode?: string | null
  disabled?: boolean
  planType?: string
}>()
/** 保存成功后同步回页面表单，避免页面持有旧的 PlanMode */
const emit = defineEmits<{ change: [value: string] }>()

const { getPlans } = usePlanApi()
const { updateUser } = useUserApi()

const busy = ref(false)
const error = ref('')
const selected = ref(props.planMode ?? 'Fixed')
const planOptions = ref<{ label: string; value: string }[]>([])
const enabled = computed(() => selected.value !== 'Fixed')
const options = computed(() => [
  { label: t('core.plan.universal.fixed'), value: 'Fixed' },
  ...planOptions.value,
])
let revision = 0

watch(
  () => props.planMode,
  value => {
    selected.value = value ?? 'Fixed'
  }
)

watch(
  () => props.scriptId,
  async () => {
    const current = ++revision
    planOptions.value = []
    error.value = ''
    busy.value = true
    try {
      const all = await getPlans(undefined, { silent: true })
      if (current !== revision) return
      if (all.code !== 200) throw new Error(t('core.plan.universal.readFailed'))
      planOptions.value = all.index.flatMap(item => {
        const info = all.data[item.uid]?.Info
        const matches = item.type === (props.planType ?? PLAN_CONFIG_TYPES.UNIVERSAL)
        const ownerMatches =
          props.planType === PLAN_CONFIG_TYPES.OKNTE ||
          props.planType === PLAN_CONFIG_TYPES.OKWW ||
          (info && 'ScriptId' in info && info.ScriptId === props.scriptId)
        return matches && ownerMatches ? [{ label: info?.Name ?? '', value: item.uid }] : []
      })
    } catch (reason) {
      if (current === revision) error.value = String(reason)
    } finally {
      if (current === revision) busy.value = false
    }
  },
  { immediate: true }
)

async function selectPlan(value: unknown) {
  if (typeof value !== 'string' || value === selected.value) return
  const previous = selected.value
  selected.value = value
  busy.value = true
  try {
    const saved = await updateUser(props.scriptId, props.userId, { Info: { PlanMode: value } })
    if (saved) emit('change', value)
    else selected.value = previous
  } finally {
    busy.value = false
  }
}

function goToPlans() {
  navigateTo('/plans', { query: enabled.value ? { planId: selected.value } : {} })
}
</script>

<style scoped>
.plans-link-col {
  display: flex;
  align-items: flex-end;
  padding-bottom: 24px;
}

.plans-button {
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
