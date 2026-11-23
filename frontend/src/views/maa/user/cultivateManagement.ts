import type { InjectionKey, Ref } from 'vue'

export const cultivateManagementKey: InjectionKey<{
  managed: Readonly<Ref<boolean>>
  managing: Readonly<Ref<boolean>>
  setManaged: (enabled: boolean) => Promise<void>
}> = Symbol('cultivateManagement')
