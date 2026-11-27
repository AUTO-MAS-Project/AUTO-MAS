<template>
  <div class="plans-header app-page-header">
    <div class="header-left">
      <h1 class="page-title app-page-title">{{ t('core.plan.title') }}</h1>
    </div>
    <div class="header-actions">
      <a-space size="middle">
        <DocLink :url="MAS_DOC_URLS.plans" />
        <a-dropdown :trigger="['click']">
          <template #overlay>
            <a-menu @click="onAddPlanMenu">
              <a-menu-item v-for="planType in availablePlanTypes" :key="planType.createType">
                {{ t('core.plan.createTyped', { name: planType.displayName }) }}
              </a-menu-item>
            </a-menu>
          </template>
          <a-button type="primary" size="large">
            {{ t('core.plan.create') }}
            <DownOutlined />
          </a-button>
        </a-dropdown>

        <ConfirmActionButton
          v-if="planList.length > 0"
          risk="low"
          tone="danger"
          size="large"
          :title="t('core.plan.deleteConfirm')"
          :disabled="!activePlanId || creating"
          :confirm="() => removePlan(activePlanId)"
        >
          <template #icon>
            <DeleteOutlined />
          </template>
          {{ t('core.plan.deleteCurrent') }}
        </ConfirmActionButton>
      </a-space>
    </div>
  </div>
  <UniversalPlanCreateDialog
    ref="ownerDialog"
    :active-plan-id="activePlanId"
    :creating="creating"
    @create="createWithOwner"
  />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useScriptCapabilities } from '@/composables/useScriptCapabilities'
import UniversalPlanCreateDialog from './UniversalPlanCreateDialog.vue'
import { useI18n } from 'vue-i18n'
import { DeleteOutlined, DownOutlined } from '@ant-design/icons-vue'
import { getAvailablePlanTypes, type PlanTypeOption } from '@/utils/planTypeRegistry'
import type { PlanListItem } from '../planList'
import { ConfirmActionButton } from '@/components/ui'
import DocLink from '@/components/DocLink.vue'
import { MAS_DOC_URLS } from '@/utils/openExternal'

const { t } = useI18n()
const capabilities = useScriptCapabilities(ref(true))
const availablePlanTypes = computed(() =>
  getAvailablePlanTypes(capabilities.types.value, capabilities.provided.value)
)

interface Props {
  planList: PlanListItem[]
  activePlanId: string
  creating?: boolean
  removePlan: (planId: string) => void | Promise<unknown>
}

defineProps<Props>()
const emit = defineEmits<{
  'add-plan': [plan: PlanTypeOption, owner?: { scriptId: string }]
}>()

const ownerDialog = ref<InstanceType<typeof UniversalPlanCreateDialog> | null>(null)
const selectedCreateType = ref<string>()
function createWithOwner(scriptId: string) {
  const plan = availablePlanTypes.value.find(
    option => option.createType === selectedCreateType.value
  )
  if (plan) emit('add-plan', plan, { scriptId })
}
const onAddPlanMenu = ({ key }: { key: string }) => {
  const plan = availablePlanTypes.value.find(option => option.createType === key)
  if (!plan) return
  if (plan.parentScriptType) {
    selectedCreateType.value = key
    void ownerDialog.value?.show(plan.parentScriptType, plan.displayName, plan.configType)
  } else emit('add-plan', plan)
}
</script>

<style scoped>
.header-left {
  flex: 1;
  min-width: 0; /* 防止文字溢出 */
}

.page-title {
  white-space: nowrap; /* 防止标题换行 */
  overflow: hidden;
  text-overflow: ellipsis; /* 长标题时显示省略号 */
}

.header-actions {
  flex-shrink: 0;
}
</style>
