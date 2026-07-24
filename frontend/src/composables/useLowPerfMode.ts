import { computed } from 'vue'
import {
  collectPerfDetectionContext,
  detectLowPerfMode,
  type V6PerfDetectionContext,
  type V6PerfMode,
} from '@/theme/v6Theme'
import { useTheme } from './useTheme'

/**
 * 低性能模式 composable。
 *
 * 设计目的：把 perfMode 状态与硬件检测细节从 useTheme 中暴露给设置页，
 * 同时保持 useTheme 作为唯一状态源（perfMode 仍由 useTheme 持有模块级 ref）。
 *
 * 返回说明：
 * - perfMode: 当前生效的性能模式（用户设置优先，缺省回退自动检测）
 * - isLowPerf: 便捷布尔值，等价于 perfMode === 'low'
 * - detectedPerfMode: 最近一次硬件检测的结果（不一定是当前生效值，用于“自动”提示）
 * - detectionContext: 当前硬件检测上下文快照（用于设置页展示 CPU/内存/reduced-motion）
 * - setPerfMode(mode): 设置性能模式，传 null 等于恢复自动检测
 * - togglePerfMode(): 在 low / normal 之间切换
 * - refreshDetection(): 重新收集硬件上下文并返回最新检测结果（不改变用户设置）
 *
 * 注意：本 composable 不持有自己的状态，所有持久化与 DOM 同步由 useTheme 负责。
 * 这避免出现两个状态源（FILE_OWNERSHIP §0.1：禁止重复状态源）。
 */
export function useLowPerfMode() {
  const {
    perfMode,
    detectedPerfMode,
    setPerfMode: setPerfModeBase,
    getDetectedPerfMode,
  } = useTheme()

  const isLowPerf = computed(() => perfMode.value === 'low')

  // 收集当前硬件上下文（用于设置页只读展示；不持久化）。
  // 注意：collectPerfDetectionContext 在非浏览器环境返回 {}，安全。
  const detectionContext: V6PerfDetectionContext = collectPerfDetectionContext()

  const togglePerfMode = () => {
    setPerfModeBase(perfMode.value === 'low' ? 'normal' : 'low')
  }

  // 重新检测：不改变用户设置，仅刷新 lastPerfDetection 快照与返回值。
  // 调用方若希望“恢复自动”，应使用 setPerfMode(null)。
  const refreshDetection = (): V6PerfMode => {
    const fresh = detectLowPerfMode(collectPerfDetectionContext())
    // useTheme 内部 lastPerfDetection 在 setPerfMode(null) 时才会被刷新；
    // 这里只返回快照，不直接修改内部状态以保持单一写入路径。
    return fresh
  }

  return {
    perfMode,
    isLowPerf,
    detectedPerfMode,
    detectionContext,
    setPerfMode: setPerfModeBase,
    togglePerfMode,
    refreshDetection,
    // 暴露最近一次缓存的检测结果（与 useTheme.getDetectedPerfMode 等价）。
    getDetectedPerfMode,
  }
}
