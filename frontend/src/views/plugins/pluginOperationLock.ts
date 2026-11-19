import { computed, readonly, shallowRef } from 'vue'

export type PluginOperationAction = 'install' | 'enable' | 'disable' | 'reload' | 'uninstall'

export interface PluginOperation {
  /** 命令目标 uid：安装为市场条目 uid，其余为注册表 uid。 */
  uid: string
  action: PluginOperationAction
}

/** 插件中心同一时刻只允许一个插件操作；安装、批量更新与启停卸载共用这把锁。 */
export function createPluginOperationLock() {
  const current = shallowRef<PluginOperation | null>(null)
  return {
    current: readonly(current),
    busy: computed(() => current.value !== null),
    /** 空闲时占用并返回 true；已有操作时返回 false，不排队。 */
    acquire(operation: PluginOperation): boolean {
      if (current.value) return false
      current.value = operation
      return true
    },
    /** 批量更新换下一项时更新当前目标，锁仍由同一批次持有。 */
    retarget(operation: PluginOperation) {
      if (current.value) current.value = operation
    },
    release() {
      current.value = null
    },
  }
}

export type PluginOperationLock = ReturnType<typeof createPluginOperationLock>
