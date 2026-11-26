<script setup lang="ts">
import { ref } from 'vue'
import UnavailableConfigCards, {
  type UnavailableConfigCard,
} from '@/components/UnavailableConfigCards.vue'
import { usePlanApi } from '@/composables/usePlanApi'

/** 计划表页里所属插件不可用的计划表：只读卡片，删除成功后从列表移除。 */
const items = defineModel<UnavailableConfigCard[]>('items', { required: true })

const logger = window.electronAPI.getLogger('计划管理')
const { deletePlan } = usePlanApi()
const deletingId = ref<string | null>(null)

const handleDelete = async (planId: string) => {
  deletingId.value = planId
  try {
    const response = await deletePlan(planId)
    if (response.code === 200) items.value = items.value.filter(item => item.uid !== planId)
  } catch (error) {
    logger.error(`删除计划失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    deletingId.value = null
  }
}
</script>

<template>
  <UnavailableConfigCards
    :items="items"
    kind="plan"
    :deleting-id="deletingId"
    @delete="handleDelete"
  />
</template>
