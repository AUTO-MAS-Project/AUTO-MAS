import type { ScriptDescriptor } from './contracts'

/** 装配时拒绝覆盖身份和入口，避免后注册的声明悄悄覆盖先注册的声明。 */
export function indexScriptDescriptors(descriptors: readonly ScriptDescriptor[]) {
  const byType = new Map<string, ScriptDescriptor>()
  const byConfigType = new Map<string, ScriptDescriptor>()
  const routeNames = new Set<string>()
  const routePaths = new Set<string>()
  const routes = descriptors.flatMap(descriptor => {
    if (byType.has(descriptor.type)) throw new Error(`重复脚本类型: ${descriptor.type}`)
    if (byConfigType.has(descriptor.configType))
      throw new Error(`重复脚本配置类型: ${descriptor.configType}`)
    byType.set(descriptor.type, descriptor)
    byConfigType.set(descriptor.configType, descriptor)
    return [...Object.values(descriptor.routes), ...descriptor.extraRoutes].map(route => {
      if (routeNames.has(route.name)) throw new Error(`重复脚本路由名称: ${route.name}`)
      if (routePaths.has(route.path)) throw new Error(`重复脚本路由路径: ${route.path}`)
      routeNames.add(route.name)
      routePaths.add(route.path)
      return route
    })
  })
  return { byType, byConfigType, routes }
}

/** 普通卡片按声明排序，flavor 沿用既有的 after 插入规则；不修改原集合。 */
export function orderScriptDescriptors(descriptors: readonly ScriptDescriptor[]) {
  const ordered = descriptors
    .filter(descriptor => descriptor.card.order !== undefined)
    .sort((left, right) => (left.card.order ?? 0) - (right.card.order ?? 0))
  for (const descriptor of descriptors.filter(item => item.card.order === undefined)) {
    const index = descriptor.card.after
      ? ordered.findIndex(item => item.type === descriptor.card.after)
      : -1
    if (index >= 0) ordered.splice(index + 1, 0, descriptor)
    else ordered.push(descriptor)
  }
  return ordered
}
