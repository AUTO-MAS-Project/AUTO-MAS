/**
 * 应用级 WebSocket 常驻资源注册表。
 *
 * 该模块只管理生命周期，不依赖页面或业务 composable。具体业务资源由组合根注册，
 * 从而保证订阅可在首个连接前统一启动，并在应用最终关闭时显式释放。
 */

export interface ResidentResource {
  bootstrap: () => void
  dispose: () => void
}

const resources = new Map<string, ResidentResource>()

export function registerResidentResource(name: string, resource: ResidentResource): void {
  if (!name.trim()) throw new Error('常驻资源名称不能为空')
  if (resources.has(name)) return
  resources.set(name, resource)
}

export function bootstrapResidentResources(): void {
  for (const resource of resources.values()) resource.bootstrap()
}

export function disposeResidentResources(): void {
  for (const resource of [...resources.values()].reverse()) resource.dispose()
}

export function residentResourceCount(): number {
  return resources.size
}
