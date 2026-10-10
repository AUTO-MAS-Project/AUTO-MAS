import { playPressSound } from '@/components/satellite/pressSound'
import { usePerformanceStore } from '@/stores/performance'
import { usePressSoundStore } from '@/stores/pressSound'
import type { PressSoundPhase } from '@/types/pressSound'

/**
 * 主页中心图标（星核）的按压音效。
 *
 * 经典卫星与 3D 星系各有一套自己的指针处理，但开关、音量与实际播放都收在这里，
 * 两边行为保持一致——加新样式时接上这个组合式函数即可。
 */
export function usePressSound() {
  const pressSoundStore = usePressSoundStore()
  const performanceStore = usePerformanceStore()
  void pressSoundStore.load()

  function play(phase: PressSoundPhase): void {
    // 低性能模式（含窗口切到后台）下装饰性音效一并停掉
    if (!pressSoundStore.enabled || performanceStore.isLowPower) {
      return
    }

    void playPressSound(
      pressSoundStore.preset,
      pressSoundStore.volume,
      pressSoundStore.customPath,
      phase,
      () => pressSoundStore.enabled && !performanceStore.isLowPower
    )
  }

  return {
    playPress: () => play('press'),
    playRelease: () => play('release'),
  }
}
