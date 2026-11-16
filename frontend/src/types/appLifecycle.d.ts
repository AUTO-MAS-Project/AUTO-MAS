/** 后端退出请求；可选字段兼容仍发送空数据的旧后端。 */
export interface FrontendCloseRequest {
  automatic?: boolean
  nextWakeAt?: string | null
}
