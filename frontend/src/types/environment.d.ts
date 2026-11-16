export type ApplicationEnvironment = 'development' | 'production'
export type BackendOwnership = 'owned' | 'external'

declare global {
  interface Window {
    /** Electron 在页面脚本执行前注入的只读运行环境。 */
    readonly appEnvironment?: ApplicationEnvironment
    /** 后端进程是否由本次 Electron 启动负责。 */
    readonly backendOwnership?: BackendOwnership
  }
}
