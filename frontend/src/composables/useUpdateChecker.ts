import { ref, onUnmounted } from 'vue'
import { Service } from '@/api'
import { getLogger } from '@/utils/logger'
import { message } from 'ant-design-vue'
import { useAudioPlayer } from '@/composables/useAudioPlayer'

const logger = getLogger('更新检查器')

// 获取版本号，优先使用环境变量，否则使用一个测试版本
const version = (import.meta as any).env.VITE_APP_VERSION || '1.0.0'

// 全局状态 - 在所有组件间共享
const updateVisible = ref(false)
const updateData = ref<Record<string, string[]>>({})
const latestVersion = ref('')

// 定时器相关 - 参考顶栏TitleBar.vue的实现
const POLL_MS = 4 * 60 * 60 * 1000 // 4小时
let updateCheckTimer: NodeJS.Timeout | null = null
const isPolling = ref(false)

// 防止重复弹出的状态
let lastShownVersion: string | null = null

// 检查自动更新设置是否开启
const checkAutoUpdateEnabled = async (): Promise<boolean> => {
  try {
    const response = await Service.getScriptsApiSettingGetPost()
    if (response.code === 200 && response.data) {
      return response.data.Update?.IfAutoUpdate || false
    }
  } catch (error) {
    logger.warn('[useUpdateChecker] 获取自动更新设置失败:', error)
  }
  return false
}

export function useUpdateChecker() {
  // 执行一次更新检查 - 完全参考顶栏的 pollOnce 逻辑
  const pollOnce = async () => {
    if (isPolling.value) return

    // 检查自动更新设置是否开启
    const autoUpdateEnabled = await checkAutoUpdateEnabled()
    if (!autoUpdateEnabled) {
      logger.info('[useUpdateChecker] 自动检查更新已关闭，跳过定时检查')
      return
    }

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

          // 播放有新版本音频
          const { playSound } = useAudioPlayer()
          await playSound('new_version_available')

          updateData.value = response.update_info
          latestVersion.value = response.latest_version
          updateVisible.value = true
          lastShownVersion = response.latest_version // 记录已显示的版本
        }
      }
    } catch (error: any) {
      logger.error('[useUpdateChecker] 定时更新检查失败:', error?.message)
    } finally {
      isPolling.value = false
    }
  }

  // 手动检查更新（用于设置页面按钮）
  const checkUpdate = async (silent = false, forceCheck = false) => {
    const { playSound } = useAudioPlayer()
    try {
      const response = await Service.checkUpdateApiUpdateCheckPost({
        current_version: version,
        if_force: forceCheck,
      })

      if (response.code === 200) {
        if (response.if_need_update) {
          // 播放有新版本音频
          await playSound('new_version_available')
          updateData.value = response.update_info
          latestVersion.value = response.latest_version
          updateVisible.value = true
        } else {
          // 播放无新版本音频
          if (!silent) {
            await playSound('no_new_version')
            message.success('暂无更新~')
          }
        }
      } else {
        if (!silent) {
          message.error(response.message || '获取更新失败')
        }
      }
    } catch (error: any) {
      logger.error('[useUpdateChecker] 手动更新检查失败:', error?.message)
      if (!silent) {
        message.error('获取更新失败！')
      }
    }
  }

  // 确认回调
  const onUpdateConfirmed = () => {
    updateVisible.value = false
  }

  // 启动定时检查器
  const startPolling = async () => {
    // 检查自动更新设置是否开启
    const autoUpdateEnabled = await checkAutoUpdateEnabled()
    if (!autoUpdateEnabled) {
      logger.info('[useUpdateChecker] 自动检查更新已关闭，不启动定时任务')
      return
    }

    // 如果已经在检查中，则不重复启动
    if (updateCheckTimer) {
      logger.info('[useUpdateChecker] 定时任务已存在，跳过启动')
      return
    }

    logger.info('[useUpdateChecker] 启动定时版本检查任务')

    // 延迟3秒后再执行首次检查，确保后端已经完全启动
    setTimeout(async () => {
      await pollOnce()
    }, 3000)

    // 每 4 小时检查一次更新
    updateCheckTimer = setInterval(pollOnce, POLL_MS)
  }

  // 停止定时检查器
  const stopPolling = () => {
    if (updateCheckTimer) {
      clearInterval(updateCheckTimer)
      updateCheckTimer = null
      logger.info('[useUpdateChecker] 停止定时版本检查任务')
    }
  }

  // 重新启动定时检查器（当设置变更时调用）
  const restartPolling = async () => {
    logger.info('[useUpdateChecker] 重新启动定时检查任务')
    stopPolling() // 先停止现有任务
    await startPolling() // 再根据设置重新启动
  }

  // 组件卸载时清理定时器
  onUnmounted(() => {
    stopPolling()
  })

  return {
    updateVisible,
    updateData,
    latestVersion,
    checkUpdate,
    onUpdateConfirmed,
    startPolling,
    stopPolling,
    restartPolling,
  }
}

// 创建一个仅用于显示弹窗的轻量版本（给App.vue使用）
export function useUpdateModal() {
  return {
    updateVisible,
    updateData,
    latestVersion,
    onUpdateConfirmed: () => {
      updateVisible.value = false
    },
  }
}
