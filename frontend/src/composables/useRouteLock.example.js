// 使用示例：在任何组件中使用路由锁定功能

import { useRouteLock } from '@/composables/useRouteLock'

export default {
  setup() {
    const { lockRoute, unlockRoute, isRouteLocked } = useRouteLock()

    // 示例1：在表单编辑时锁定路由
    const startEditing = () => {
      lockRoute(targetRoute => {
        // 用户尝试切换路由时的回调
        console.log(`用户尝试切换到 ${targetRoute}，但表单正在编辑中`)

        // 可以显示确认对话框
        if (confirm('表单正在编辑中，确定要离开吗？')) {
          unlockRoute() // 解锁路由
          // 然后可以手动导航到目标路由
          router.push(targetRoute)
        }
      })
    }

    // 示例2：保存完成后解锁路由
    const saveForm = async () => {
      try {
        // 保存逻辑...
        await saveData()

        // 保存成功后解锁路由
        unlockRoute()
      } catch (error) {
        console.error('保存失败', error)
      }
    }

    // 示例3：取消编辑时解锁路由
    const cancelEdit = () => {
      unlockRoute()
    }

    return {
      startEditing,
      saveForm,
      cancelEdit,
      isRouteLocked,
    }
  },
}
