import type { MaaFWOptionInputInfo } from '@/types/script'

/** PI v2.10.0：密码 / 密钥字段。界面只用掩码框、不回显已保存的值。 */
export const isPasswordInput = (inputItem: MaaFWOptionInputInfo) => inputItem.password === true

/** 已保存的密码字段在前端只拿得到密文；非空就算「已设置」。 */
export const hasStoredSecret = (value: string | undefined | null) => Boolean(value)
