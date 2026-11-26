<script setup lang="ts">
import { ref } from 'vue'
import UnavailableConfigCards, {
  type UnavailableConfigCard,
} from '@/components/UnavailableConfigCards.vue'
import { useScriptApi } from '@/composables/useScriptApi'

/** 托管页里所属插件不可用的托管：只读卡片，删除成功后从列表移除。 */
const items = defineModel<UnavailableConfigCard[]>('items', { required: true })

const { deleteScript } = useScriptApi()
const deletingId = ref<string | null>(null)

const handleDelete = async (scriptId: string) => {
  deletingId.value = scriptId
  try {
    if (await deleteScript(scriptId))
      items.value = items.value.filter(item => item.uid !== scriptId)
  } finally {
    deletingId.value = null
  }
}
</script>

<template>
  <UnavailableConfigCards
    :items="items"
    kind="script"
    :deleting-id="deletingId"
    @delete="handleDelete"
  />
</template>
