import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { HotUpdateRecord } from '@/types/electron'

export const useBackendHotUpdateStore = defineStore('backendHotUpdate', () => {
  const record = ref<HotUpdateRecord | null>(null)
  const blocked = ref(false)
  const recoveryVisible = ref(false)
  const retrying = ref(false)
  const retryError = ref<string | null>(null)
  return { record, blocked, recoveryVisible, retrying, retryError }
})
