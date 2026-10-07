import { Service } from '@/api'
import type { OutBase, QrCheckOut, QrCreateOut } from '@/api'
import { OpenAPI } from '@/api/core/OpenAPI'
import { request } from '@/api/core/request'

/** 森空岛确认态返回的一次性 scanCode。 */
export type SklandQrCheckOut = QrCheckOut & { scan_code?: string }

/** 神秘入口中的 Token 获取接口，沿用已有后端契约。 */
export function useTokenApi() {
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

  const loginTaygedo = (accountId: string, phone: string, password: string) =>
    Service.loginTaygedoApiToolsSignAccountTaygedoLoginPost({ accountId, phone, password })

  return {
    createMiyousheQr,
    checkMiyousheQr,
    saveMiyousheQr,
    createSklandQr,
    checkSklandQr,
    saveSklandQr,
    loginTaygedo,
  }
}
