import { watch } from 'vue'
import { dropPendingRelease, playPressSound } from '@/components/satellite/pressSound'
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

    void playPressSound({
      preset: pressSoundStore.preset,
      volume: pressSoundStore.volume,
      customPath: pressSoundStore.customPath,
      customReleasePath: pressSoundStore.customReleasePath,
      phase,
      shouldPlay: () => pressSoundStore.enabled && !performanceStore.isLowPower,
    })
  }

  // 松开音排在按压音后面播：等待期间关了开关、切了后台或开了低性能，就把它作废
  watch(
    () => pressSoundStore.enabled && !performanceStore.isLowPower,
    allowed => {
      if (!allowed) {
        dropPendingRelease()
      }
    }
  )

  return {
    playPress: () => play('press'),
    playRelease: () => play('release'),
  }
}
