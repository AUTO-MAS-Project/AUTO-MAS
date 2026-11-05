/**
 * 初始化服务 - 统一导出
 *
 * 使用示例:
 *
 * ```typescript
 * import { InitializationService } from './services'
 *
 * const initService = new InitializationService(appRoot)
 *
 * const result = await initService.initialize((progress) => {
 *   console.log(`[${progress.stage}] ${progress.message} - ${progress.progress}%`)
 * })
 *
 * if (result.success) {
 *   console.log('初始化成功')
 * } else {
 *   console.error('初始化失败:', result.error)
 * }
 * ```
 */

// 初始化总流程服务
export { InitializationService } from './initializationService'
