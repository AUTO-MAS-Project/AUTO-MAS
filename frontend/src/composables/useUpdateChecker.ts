import { ref, onMounted, onUnmounted } from 'vue'
import { Service } from '@/api'
import { message } from 'ant-design-vue'

// 获取版本号，优先使用环境变量，否则使用一个测试版本
const version = (import.meta as any).env.VITE_APP_VERSION || '1.0.0'

// 全局状态 - 在所有组件间共享
const updateVisible = ref(false)
const updateData = ref<Record<string, string[]>>({})

// 定时器相关 - 参考顶栏TitleBar.vue的实现
const POLL_MS = 4 * 60 * 60 * 1000 // 4小时
let updateCheckTimer: NodeJS.Timeout | null = null
const isPolling = ref(false)

// 防止重复弹出的状态
let lastShownVersion: string | null = null

export function useUpdateChecker() {
  
  // 执行一次更新检查 - 完全参考顶栏的 pollOnce 逻辑
  const pollOnce = async () => {
    if (isPolling.value) return
    isPolling.value = true
    
    try {
      const response = await Service.checkUpdateApiUpdateCheckPost({
        current_version: version,
        if_force: false, // 定时检查不强制获取，和顶栏一致
      })
      
      if (response.code === 200) {
        if (response.if_need_update) {
          // 检查是否已经有更新弹窗在显示，避免重复弹出
          if (updateVisible.value) {
            return
          }
          
          // 检查是否为同一版本，避免同一版本重复弹出
          if (lastShownVersion === response.latest_version) {
            return
          }
          
          updateData.value = response.update_info
          updateVisible.value = true
          lastShownVersion = response.latest_version // 记录已显示的版本
        }
      }
    } catch (error: any) {
      console.error('[useUpdateChecker] 定时更新检查失败:', error?.message)
    } finally {
      isPolling.value = false
    }
  }

  // 手动检查更新（用于设置页面按钮）
  const checkUpdate = async (silent = false, forceCheck = false) => {
    try {
      const response = await Service.checkUpdateApiUpdateCheckPost({
        current_version: version,
        if_force: forceCheck,
      })
      
      if (response.code === 200) {
        if (response.if_need_update) {
          updateData.value = response.update_info
          updateVisible.value = true
        } else {
          if (!silent) {
            message.success('暂无更新~')
          }
        }
      } else {
        if (!silent) {
          message.error(response.message || '获取更新失败')
        }
      }
    } catch (error: any) {
      console.error('[useUpdateChecker] 手动更新检查失败:', error?.message)
      if (!silent) {
        message.error('获取更新失败！')
      }
    }
  }

  // 确认回调
  const onUpdateConfirmed = () => {
    updateVisible.value = false
  }

  // 组件挂载时启动检查器 - 参考顶栏的 onMounted 逻辑
  onMounted(async () => {
    // 延迟3秒后再执行首次检查，确保后端已经完全启动
    setTimeout(async () => {
      await pollOnce()
    }, 3000)
    
    // 每 4 小时检查一次更新
    updateCheckTimer = setInterval(pollOnce, POLL_MS)
  })

  // 组件卸载时清理定时器 - 参考顶栏的 onBeforeUnmount 逻辑
  onUnmounted(() => {
    if (updateCheckTimer) {
      clearInterval(updateCheckTimer)
      updateCheckTimer = null
    }
  })

  return {
    updateVisible,
    updateData,
    checkUpdate,
    onUpdateConfirmed
  }
}
