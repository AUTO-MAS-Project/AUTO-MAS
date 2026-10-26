export type ApplicationEnvironment = 'development' | 'production'

declare global {
  interface Window {
    /** Electron 在页面脚本执行前注入的只读运行环境。 */
    readonly appEnvironment?: ApplicationEnvironment
  }
}
