import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { useGameSignAccountApi } from '@/composables/useGameSignAccountApi'
import { useGameSignApi } from './useGameSignApi'
import {
  buildUserTagsMap,
  parseSignResult,
  type PlatformResult,
  type PlatformTag,
} from './gameSignDisplay'
import { asRecord, asString, toAccountForm, type AccountInstance } from './gameSignAccounts'

interface AccountListEntry {
  uid?: unknown
}

interface AccountListData {
  order?: AccountListEntry[]
  data?: Record<string, unknown>
}

/**
 * 游戏社区帐号与签到结果的页面状态。
 *
 * 签到页和帐号管理页都要读同一份帐号列表和签到结果，但两个页签互斥渲染，
 * 所以各自持有一份实例即可：切换页签时重新加载，避免编辑后残留旧快照。
 * 提交一律走 diffAccountForm 产出的补丁，不整份回写。
 */
export function useGameSignAccounts(resultSource: () => string | null | undefined) {
  const logger = window.electronAPI.getLogger('游戏社区')
  const { addAccount, updateAccount, deleteAccount } = useGameSignAccountApi()
  const { listAccounts, reorderAccounts } = useGameSignApi()

  const accounts = ref<AccountInstance[]>([])
  const loading = ref(false)
  const reordering = ref(false)

  const load = async () => {
    loading.value = true
    try {
      const response = await listAccounts()
      if (response.code !== 200) return
      const data = response.data as unknown as AccountListData | undefined
      const entries = Array.isArray(data?.order) ? data.order : []
      const next: AccountInstance[] = []
      for (const entry of entries) {
        const uid = asString(entry.uid)
        if (!uid) continue
        const raw = asRecord(asRecord(data?.data?.[uid]).GameSignAccount)
        next.push({
          uid,
          Name: asString(raw.Name) || t('core.gamesign.defaultUserName'),
          Enabled: typeof raw.Enabled === 'boolean' ? raw.Enabled : true,
          MiyousheToken: asString(raw.MiyousheToken),
          MiyousheDeviceId: asString(raw.MiyousheDeviceId),
          MiyousheDeviceFp: asString(raw.MiyousheDeviceFp),
          CloudGenshinToken: asString(raw.CloudGenshinToken),
          KuroToken: asString(raw.KuroToken),
          SklandToken: asString(raw.SklandToken),
          TaygedoToken: asString(raw.TaygedoToken),
        })
      }
      accounts.value = next
    } catch (error) {
      logger.error(`加载账号列表失败: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      loading.value = false
    }
  }

  const signResult = computed<PlatformResult>(() => parseSignResult(resultSource()))
  const userTagsMap = computed<Map<string, PlatformTag[]>>(() =>
    buildUserTagsMap(accounts.value, signResult.value)
  )

  /** 新建帐号并立刻返回本地实例，调用方随后打开编辑抽屉 */
  const createAccount = async (): Promise<AccountInstance | null> => {
    const created = await addAccount()
    if (!created) return null
    const data = created.data
    const account: AccountInstance = {
      uid: created.accountId,
      Name: data.Name || t('core.gamesign.newUserName', { n: accounts.value.length + 1 }),
      Enabled: data.Enabled ?? true,
      MiyousheToken: data.MiyousheToken || '',
      MiyousheDeviceId: data.MiyousheDeviceId || '',
      MiyousheDeviceFp: data.MiyousheDeviceFp || '',
      CloudGenshinToken: data.CloudGenshinToken || '',
      KuroToken: data.KuroToken || '',
      SklandToken: data.SklandToken || '',
      TaygedoToken: data.TaygedoToken || '',
    }
    accounts.value = [...accounts.value, account]
    message.success(t('core.gamesign.toast.userAdded'))
    return account
  }

  /** 只提交改动字段；没有改动时直接返回成功，不发请求 */
  const saveAccount = async (
    account: AccountInstance,
    patch: Record<string, unknown>
  ): Promise<boolean> => {
    if (Object.keys(patch).length === 0) return true
    try {
      await updateAccount(account.uid, patch)
      Object.assign(account, patch)
      return true
    } catch {
      message.error(t('core.gamesign.toast.saveFailed'))
      return false
    }
  }

  const removeAccount = async (account: AccountInstance): Promise<void> => {
    try {
      await deleteAccount(account.uid)
      accounts.value = accounts.value.filter(item => item.uid !== account.uid)
    } catch {
      // deleteAccount 已提示失败原因，这里保持列表不动
    }
  }

  const toggleEnabled = async (account: AccountInstance, enabled: boolean): Promise<void> => {
    const previous = account.Enabled
    account.Enabled = enabled
    try {
      await updateAccount(account.uid, { Enabled: enabled })
    } catch {
      account.Enabled = previous
      message.error(t('core.gamesign.toast.saveFailed'))
    }
  }

  /** 拖拽结束后按给定顺序提交，失败时重新拉取以恢复服务端顺序 */
  const reorder = async (order?: string[]): Promise<void> => {
    reordering.value = true
    const nextOrder = order ?? accounts.value.map(item => item.uid)
    if (order) {
      // 先按新顺序落到本地，失败回滚由下面的 load() 负责
      const byUid = new Map(accounts.value.map(item => [item.uid, item]))
      const reordered = nextOrder
        .map(uid => byUid.get(uid))
        .filter((item): item is AccountInstance => item !== undefined)
      if (reordered.length === accounts.value.length) {
        accounts.value = reordered
      }
    }
    try {
      const response = await reorderAccounts(nextOrder)
      if (response.code !== 200) {
        throw new Error(response.message || t('core.gamesign.toast.reorderFailed'))
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error)
      logger.error(`保存账号排序失败: ${errorMessage}`)
      message.error(t('core.gamesign.toast.reorderError', { error: errorMessage }))
      await load()
    } finally {
      reordering.value = false
    }
  }

  return {
    accounts,
    loading,
    reordering,
    signResult,
    userTagsMap,
    load,
    createAccount,
    saveAccount,
    removeAccount,
    toggleEnabled,
    reorder,
    toAccountForm,
  }
}
