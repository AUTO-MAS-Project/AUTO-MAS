import { Service } from '@/api'

/** 新版游戏社区页使用的业务 API。 */
export function useGameSignApi() {
  const listAccounts = () => Service.listGameSignAccountsApiToolsSignAccountListPost()

  const reorderAccounts = (order: string[]) =>
    Service.reorderGameSignAccountsApiToolsSignAccountReorderPost({ order })

  const manualSign = () => Service.manualGameSignApiToolsSignPost()

  const createMiyousheQr = () => Service.qrCreateApiToolsSignMiyousheQrCreatePost()

  const checkMiyousheQr = (ticket: string, device: string) =>
    Service.qrCheckApiToolsSignMiyousheQrCheckPost({ ticket, device })

  const saveMiyousheQr = (accountUid: string, cookie: string) =>
    Service.qrSaveApiToolsSignMiyousheQrSavePost({
      account_uid: accountUid,
      cookie,
    })

  return {
    listAccounts,
    reorderAccounts,
    manualSign,
    createMiyousheQr,
    checkMiyousheQr,
    saveMiyousheQr,
  }
}
