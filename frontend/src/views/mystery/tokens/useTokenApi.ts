import { Service } from '@/api'

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

  const createSklandQr = () => Service.qrCreateApiToolsSignSklandQrCreatePost()

  const checkSklandQr = (ticket: string, device: string) =>
    Service.qrCheckApiToolsSignSklandQrCheckPost({ ticket, device })

  const saveSklandQr = (accountUid: string, scanCode: string) =>
    Service.qrSaveApiToolsSignSklandQrSavePost({
      account_uid: accountUid,
      scan_code: scanCode,
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
