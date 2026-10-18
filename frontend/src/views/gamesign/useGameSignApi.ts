import { Service } from '@/api'

/** 游戏社区账号与签到 API。 */
export function useGameSignApi() {
  const listAccounts = () => Service.listGameSignAccountsApiToolsSignAccountListPost()

  const reorderAccounts = (order: string[]) =>
    Service.reorderGameSignAccountsApiToolsSignAccountReorderPost({ order })

  const manualSign = () => Service.manualGameSignApiToolsSignPost()

  return { listAccounts, reorderAccounts, manualSign }
}
