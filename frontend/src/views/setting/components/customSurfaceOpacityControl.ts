import { computed, ref } from 'vue'
import { clampCustomSurfaceOpacity } from '@/utils/customBackground'

type CustomSurfaceOpacityPersistence = {
  readValue: () => number
  previewValue: (value: number) => void
  saveValue: (value: number) => Promise<void>
  onSaveError: () => void
}

export function createCustomSurfaceOpacityControl(persistence: CustomSurfaceOpacityPersistence) {
  const previewValue = ref<number | null>(null)
  let changeRevision = 0
  const displayedValue = computed(() => previewValue.value ?? persistence.readValue())

  const startPreview = (value: number): void => {
    changeRevision += 1
    const nextValue = clampCustomSurfaceOpacity(value)
    previewValue.value = nextValue
    persistence.previewValue(nextValue)
  }

  const commitValue = async (value: number): Promise<void> => {
    const revision = ++changeRevision
    const targetValue = clampCustomSurfaceOpacity(value)
    previewValue.value = targetValue

    try {
      await persistence.saveValue(targetValue)
    } catch {
      persistence.onSaveError()
    } finally {
      if (revision === changeRevision) {
        previewValue.value = null
      }
    }
  }

  return {
    displayedValue,
    startPreview,
    commitValue,
  }
}
