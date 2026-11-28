<script setup lang="ts">
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { StateView } from '@/components/ui'
import { useUserApi } from '@/composables/useUserApi'

const props = defineProps<{ scriptId: string; scriptType: string }>()
const route = useRoute()
const router = useRouter()
const { addUser } = useUserApi()

watch(
  () => [props.scriptId, props.scriptType] as const,
  async ([scriptId, scriptType], _, onCleanup) => {
    let current = true
    onCleanup(() => {
      current = false
    })
    const user = await addUser(scriptId)
    if (!current) return
    await router.replace(
      user?.userId
        ? {
            name: 'GenericUserEdit',
            params: { scriptId, scriptType, userId: user.userId },
            query: route.query,
            hash: route.hash,
          }
        : { name: 'Scripts' }
    )
  },
  { immediate: true }
)
</script>

<template>
  <StateView loading />
</template>
