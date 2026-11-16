import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'
import { Service } from '@/api'
import { communitySignOutcome } from '@/utils/communityAnalytics'

/** 游戏社区账号与签到 API。 */
export function useGameSignApi() {
  const listAccounts = () => Service.listGameSignAccountsApiToolsSignAccountListPost()

  const reorderAccounts = (order: string[]) =>
    observeFeature(
      'community_account_manage_finished',
      { action: 'reorder' },
      () => Service.reorderGameSignAccountsApiToolsSignAccountReorderPost({ order }),
      apiOutcome
    )

  const manualSign = () =>
    observeFeature(
      'game_sign_requested',
      { trigger_kind: 'manual' },
      () => Service.manualGameSignApiToolsSignPost(),
      communitySignOutcome
    )

  return { listAccounts, reorderAccounts, manualSign }
}
