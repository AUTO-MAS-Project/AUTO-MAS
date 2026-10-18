import { describe, expect, it, vi } from 'vite-plus/test'
import { ref } from 'vue'
import { createCustomSurfaceOpacityControl } from './customSurfaceOpacityControl'

describe('customSurfaceOpacityControl', () => {
  it('previews drag values and persists only the committed value', async () => {
    const persistedValue = ref(0.8)
    const saveValue = vi.fn(async (value: number) => {
      persistedValue.value = value
    })
    const control = createCustomSurfaceOpacityControl({
      readValue: () => persistedValue.value,
      previewValue: value => {
        persistedValue.value = value
      },
      saveValue,
      onSaveError: () => undefined,
    })

    control.startPreview(0.4)

    expect(control.displayedValue.value).toBe(0.4)
    expect(saveValue).not.toHaveBeenCalled()

    await control.commitValue(0.55)

    expect(saveValue).toHaveBeenCalledTimes(1)
    expect(saveValue).toHaveBeenCalledWith(0.55)
    expect(control.displayedValue.value).toBe(0.55)
  })

  it('keeps a newer preview while an older commit is still saving', async () => {
    const persistedValue = ref(0.8)
    let resolveFirstSave: (() => void) | undefined
    const saveValue = vi.fn((value: number) => {
      persistedValue.value = value
      if (saveValue.mock.calls.length === 1) {
        return new Promise<void>(resolve => {
          resolveFirstSave = resolve
        })
      }
      return Promise.resolve()
    })
    const control = createCustomSurfaceOpacityControl({
      readValue: () => persistedValue.value,
      previewValue: value => {
        persistedValue.value = value
      },
      saveValue,
      onSaveError: () => undefined,
    })

    const firstSave = control.commitValue(0.4)
    control.startPreview(0.45)
    const secondSave = control.commitValue(0.5)

    resolveFirstSave?.()
    await firstSave

    expect(control.displayedValue.value).toBe(0.5)

    await secondSave

    expect(control.displayedValue.value).toBe(0.5)
  })
})
