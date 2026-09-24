import { Service } from '@/api'
import type { OutBase, QrCheckOut, QrCreateOut } from '@/api'
import { OpenAPI } from '@/api/core/OpenAPI'
import { request } from '@/api/core/request'

/** 森空岛确认态补充返回的一次性 scanCode；生成客户端更新前先在此收敛扩展字段。 */
export type SklandQrCheckOut = QrCheckOut & { scan_code?: string }

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

  // 森空岛扫码接口尚未进入当前生成的 OpenAPI Service；生成更新前用统一 request 包装。
  const createSklandQr = () =>
    request<QrCreateOut>(OpenAPI, {
      method: 'POST',
      url: '/api/tools/sign/skland/qr/create',
    })

  const checkSklandQr = (ticket: string, device: string) =>
    request<SklandQrCheckOut>(OpenAPI, {
      method: 'POST',
      url: '/api/tools/sign/skland/qr/check',
      body: { ticket, device },
      mediaType: 'application/json',
    })

  const saveSklandQr = (accountUid: string, scanCode: string) =>
    request<OutBase>(OpenAPI, {
      method: 'POST',
      url: '/api/tools/sign/skland/qr/save',
      body: { account_uid: accountUid, scan_code: scanCode },
      mediaType: 'application/json',
    })

  return {
    listAccounts,
    reorderAccounts,
    manualSign,
    createMiyousheQr,
    checkMiyousheQr,
    saveMiyousheQr,
    createSklandQr,
    checkSklandQr,
    saveSklandQr,
  }
}
