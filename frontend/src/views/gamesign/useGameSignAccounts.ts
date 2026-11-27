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
 * 帐号列表是签到页和帐号管理页共用的同一份数据，因此状态放在模块级。
 *
 * 两个页签互斥渲染，但签到页要展示的"凭据是否已绑定"、签名结果里的账号名，
 * 都来自帐号列表；各持一份实例会让帐号管理页改完名字、停用或新增帐号后，
 * 切回签到页仍然显示旧数据。结果解析（signResult）仍跟着各自的配置来源走。
 * 提交一律走 diffAccountForm 产出的补丁，不整份回写。
 */
const sharedAccounts = ref<AccountInstance[]>([])
const sharedLoading = ref(false)
const sharedReordering = ref(false)

/** 拉一次服务端快照并解析成帐号实例，失败返回 null（由调用方决定是保留旧值还是报错） */
const fetchAccountList = async (): Promise<AccountInstance[] | null> => {
  const { listAccounts } = useGameSignApi()
  const response = await listAccounts()
  if (response.code !== 200) return null
  const data = response.data as unknown as AccountListData | undefined
  const entries = Array.isArray(data?.order) ? data.order : []
  const next: AccountInstance[] = []
  for (const entry of entries) {
    const uid = asString(entry.uid)
    if (!uid) continue
    const raw = asRecord(asRecord(data?.data?.[uid]).SignFlowAccount)
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
  return next
}

export function useGameSignAccounts(resultSource: () => string | null | undefined) {
  const logger = window.electronAPI.getLogger('游戏社区')
  const { addAccount, updateAccount, deleteAccount } = useGameSignAccountApi()
  const { reorderAccounts } = useGameSignApi()

  const accounts = sharedAccounts
  const loading = sharedLoading
  const reordering = sharedReordering

  const load = async () => {
    loading.value = true
    try {
      const next = await fetchAccountList()
      if (!next) {
        // 业务码非 200 时不抛异常，只返回 null；完全静默会让页面留着上一次的帐号
        message.error(t('core.gamesign.toast.loadAccountsFailed'))
        return
      }
      accounts.value = next
    } catch (error) {
      logger.error(`加载账号列表失败: ${error instanceof Error ? error.message : String(error)}`)
      message.error(t('core.gamesign.toast.loadAccountsFailed'))
    } finally {
      loading.value = false
    }
  }

  /**
   * 按帐号 UID 回读单个帐号。
   *
   * 扫码和账密登录都由后端直接写库，前端拿到的只是扫码票据这类一次性参数，
   * 所以这两个流程结束后必须回读已保存的字段，不能把回调参数当成凭据。
   */
  const reloadAccount = async (uid: string): Promise<AccountInstance | null> => {
    try {
      const next = await fetchAccountList()
      if (!next) return null
      accounts.value = next
      return next.find(item => item.uid === uid) ?? null
    } catch (error) {
      logger.error(`回读账号失败: ${error instanceof Error ? error.message : String(error)}`)
      // 扫码 / 账密 / 短信都已经在后端落库，回读失败只影响界面显示，
      // 但用户会以为绑定没生效，因此这里必须给一句可见提示。
      message.error(t('core.gamesign.toast.loadAccountsFailed'))
      return null
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
    reloadAccount,
    toAccountForm,
  }
}
