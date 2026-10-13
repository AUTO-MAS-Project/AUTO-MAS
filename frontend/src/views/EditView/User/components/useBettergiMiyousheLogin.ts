import { computed, reactive, ref, watch } from 'vue'
import type {
  BetterGIUserConfig_Switch,
  MiyousheGenshinAccountOut,
  MiyousheGenshinRoleOut,
} from '@/api'
import { useMiyousheGenshinApi } from '@/composables/useMiyousheGenshinApi'

type LoginField = 'MiyousheLogin' | 'MiyousheAccountUid' | 'MiyousheRoleUid' | 'MiyousheRoleRegion'
export type LoginSettings = {
  [K in LoginField]-?: NonNullable<BetterGIUserConfig_Switch[K]>
}

export interface MiyousheLoginProps {
  config: LoginSettings
  resource: string
  clientChannel: string
  disabled?: boolean
  onSave: (data: Partial<LoginSettings>) => Promise<boolean>
}

/** 账号与角色一起保存，未完成的选择不会覆盖已保存配置。 */
export function useBettergiMiyousheLogin(
  props: MiyousheLoginProps,
  onPersisted: (enabled: boolean) => void,
  errorText: (cause: unknown) => string
) {
  const { accountsLoading, rolesLoading, getAccounts, getRoles } = useMiyousheGenshinApi()
  const pickSettings = (): LoginSettings => ({
    MiyousheLogin: props.config.MiyousheLogin,
    MiyousheAccountUid: props.config.MiyousheAccountUid,
    MiyousheRoleUid: props.config.MiyousheRoleUid,
    MiyousheRoleRegion: props.config.MiyousheRoleRegion,
  })
  const draft = reactive(pickSettings())
  const saved = ref(pickSettings())
  const accounts = ref<MiyousheGenshinAccountOut[]>([])
  const roles = ref<MiyousheGenshinRoleOut[]>([])
  const accountsLoaded = ref(false)
  const rolesLoaded = ref(false)
  const accountError = ref('')
  const roleError = ref('')
  const saveFailed = ref(false)
  const saving = ref(false)
  let roleRequest = 0
  let accountRequest = 0
  let pendingEnable = false
  let mounted = true

  const officialClient = computed(
    () => props.resource === '官服' && (!props.clientChannel || props.clientChannel === '官服')
  )
  const selectedAccount = computed(() =>
    accounts.value.find(account => account.uid === draft.MiyousheAccountUid)
  )
  const accountMissing = computed(
    () => accountsLoaded.value && !!draft.MiyousheAccountUid && !selectedAccount.value
  )
  const selectedRole = computed(() =>
    roles.value.find(
      role => role.uid === draft.MiyousheRoleUid && role.region === draft.MiyousheRoleRegion
    )
  )
  const dirty = computed(() =>
    (Object.keys(saved.value) as LoginField[]).some(key => draft[key] !== saved.value[key])
  )
  const canSave = computed(
    () => officialClient.value && !!selectedAccount.value?.has_credentials && !!selectedRole.value
  )
  watch(
    () => [draft.MiyousheLogin, draft.MiyousheAccountUid] as const,
    ([enabled, accountUid]) => {
      if (enabled && accountUid) void loadRoles(accountUid)
      else {
        roleRequest += 1
        roles.value = []
        rolesLoaded.value = false
        roleError.value = ''
      }
    }
  )

  async function initialize() {
    await loadAccounts()
    if (mounted && draft.MiyousheLogin && draft.MiyousheAccountUid) {
      await loadRoles(draft.MiyousheAccountUid)
    }
  }

  function dispose() {
    mounted = false
    roleRequest += 1
    accountRequest += 1
  }

  async function loadAccounts() {
    const request = ++accountRequest
    accountError.value = ''
    try {
      const data = await getAccounts()
      if (!mounted || request !== accountRequest) return
      accounts.value = data
      accountsLoaded.value = true
      if (pendingEnable && canSave.value) {
        pendingEnable = false
        await saveSettings()
      }
    } catch (cause) {
      if (mounted && request === accountRequest) accountError.value = errorText(cause)
    }
  }

  async function loadRoles(accountUid: string) {
    const request = ++roleRequest
    roles.value = []
    rolesLoaded.value = false
    roleError.value = ''
    try {
      const data = await getRoles(accountUid)
      if (!mounted || request !== roleRequest || accountUid !== draft.MiyousheAccountUid) return
      roles.value = data.filter(role => role.region === 'cn_gf01')
      rolesLoaded.value = true
      if (pendingEnable && canSave.value) {
        pendingEnable = false
        await saveSettings()
      }
    } catch (cause) {
      if (mounted && request === roleRequest && accountUid === draft.MiyousheAccountUid) {
        roleError.value = errorText(cause)
      }
    }
  }

  async function saveSettings() {
    if (saving.value || props.disabled || (draft.MiyousheLogin && !canSave.value)) return
    const data = draft.MiyousheLogin ? { ...draft } : { MiyousheLogin: false }
    saving.value = true
    saveFailed.value = false
    try {
      const ok = await props.onSave(data)
      if (!mounted) return
      saveFailed.value = !ok
      if (ok) {
        saved.value = { ...saved.value, ...data }
        onPersisted(data.MiyousheLogin)
      }
    } catch {
      if (mounted) saveFailed.value = true
    } finally {
      if (mounted) saving.value = false
    }
  }

  function changeEnabled(enabled: boolean) {
    if (enabled && !officialClient.value) return
    draft.MiyousheLogin = enabled
    pendingEnable = enabled
    saveFailed.value = false
    if (!enabled) {
      // 关闭新登录方式时保留已保存的账号/角色，不把未完成的选择写成空值。
      draft.MiyousheAccountUid = saved.value.MiyousheAccountUid
      draft.MiyousheRoleUid = saved.value.MiyousheRoleUid
      draft.MiyousheRoleRegion = saved.value.MiyousheRoleRegion
      void saveSettings()
    }
  }

  function changeAccount(accountUid: string) {
    pendingEnable = false
    draft.MiyousheAccountUid = accountUid
    draft.MiyousheRoleUid = ''
    draft.MiyousheRoleRegion = ''
    saveFailed.value = false
  }

  function changeRole(roleUid: string) {
    const role = roles.value.find(item => item.uid === roleUid && item.region === 'cn_gf01')
    if (!role) return
    draft.MiyousheRoleUid = role.uid
    draft.MiyousheRoleRegion = role.region
    pendingEnable = false
    void saveSettings()
  }

  return {
    accountsLoading,
    rolesLoading,
    draft,
    saved,
    accounts,
    roles,
    accountsLoaded,
    rolesLoaded,
    accountError,
    roleError,
    saveFailed,
    saving,
    officialClient,
    selectedAccount,
    accountMissing,
    selectedRole,
    dirty,
    canSave,
    initialize,
    dispose,
    loadAccounts,
    loadRoles,
    saveSettings,
    changeEnabled,
    changeAccount,
    changeRole,
  }
}
