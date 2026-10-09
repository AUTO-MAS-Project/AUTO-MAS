import type { ScreenPoint } from './satelliteScene'

/**
 * star / rainbow：按中心冒的 star!；hint：小提示；huge：彩蛋大字；love：粉色大字；
 * speech：角色台词气泡，停得久一些
 */
export type FloatTextVariant = 'star' | 'rainbow' | 'hint' | 'huge' | 'love' | 'speech'

/** 同时在飞的浮字上限；快速连点时先到的先让位，免得 DOM 和合成层无限堆 */
const MAX_FLOAT_TEXTS = 12

/** 左右随机偏一点，整体向上；缓动是强 ease-in，越飞越快 */
function riseAway(element: HTMLSpanElement): Animation {
  const driftX = (Math.random() - 0.5) * 90
  const riseY = 220 + Math.random() * 140
  const spin = (Math.random() - 0.5) * 50
  return element.animate(
    [
      { transform: 'translate(-50%, -50%) scale(0.6)', opacity: 0 },
      {
        offset: 0.22,
        transform: `translate(calc(-50% + ${driftX * 0.3}px), calc(-50% - ${riseY * 0.3}px)) scale(1.08) rotate(${spin * 0.35}deg)`,
        opacity: 1,
      },
      {
        transform: `translate(calc(-50% + ${driftX}px), calc(-50% - ${riseY}px)) scale(0.92) rotate(${spin}deg)`,
        opacity: 0,
      },
    ],
    { duration: 1150, easing: 'cubic-bezier(0.5, 0, 1, 1)', fill: 'forwards' }
  )
}

/** 彩蛋大字：原地弹出来，停一会儿再往上淡掉 */
function popUp(element: HTMLSpanElement): Animation {
  return element.animate(
    [
      { transform: 'translate(-50%, -50%) scale(0.2)', opacity: 0 },
      { offset: 0.18, transform: 'translate(-50%, -50%) scale(1.25)', opacity: 1 },
      { offset: 0.3, transform: 'translate(-50%, -50%) scale(0.95)', opacity: 1 },
      { offset: 0.8, transform: 'translate(-50%, -60%) scale(1)', opacity: 1 },
      { transform: 'translate(-50%, -90%) scale(1.05)', opacity: 0 },
    ],
    { duration: 1900, easing: 'ease-out', fill: 'forwards' }
  )
}

/** 台词气泡：从卫星上方冒出来，停三秒多再飘走 */
function speak(element: HTMLSpanElement): Animation {
  return element.animate(
    [
      { transform: 'translate(-50%, -100%) scale(0.6)', opacity: 0 },
      { offset: 0.08, transform: 'translate(-50%, calc(-100% - 46px)) scale(1)', opacity: 1 },
      { offset: 0.85, transform: 'translate(-50%, calc(-100% - 52px)) scale(1)', opacity: 1 },
      { transform: 'translate(-50%, calc(-100% - 70px)) scale(0.96)', opacity: 0 },
    ],
    { duration: 3600, easing: 'ease-out', fill: 'forwards' }
  )
}

/**
 * 卫星区域里冒出来的浮字。样式（.star-burst 及各变体）写在 SatelliteAnimation.vue 里，
 * 用 :deep 管到这些运行时创建的节点。
 */
export function createFloatTextLayer() {
  const active: HTMLSpanElement[] = []

  function remove(element: HTMLSpanElement): void {
    element.getAnimations().forEach(animation => animation.cancel())
    element.remove()
  }

  /** 在 host 里 point 处冒一句字 */
  function spawn(
    host: HTMLElement,
    point: ScreenPoint,
    text: string,
    variant: FloatTextVariant
  ): void {
    const element = document.createElement('span')
    element.className = `star-burst star-burst-${variant}`
    element.textContent = text
    element.style.left = `${point.x}px`
    element.style.top = `${point.y}px`
    host.appendChild(element)
    active.push(element)

    while (active.length > MAX_FLOAT_TEXTS) {
      const oldest = active.shift()
      if (oldest) {
        remove(oldest)
      }
    }

    const animation =
      variant === 'huge' || variant === 'love'
        ? popUp(element)
        : variant === 'speech'
          ? speak(element)
          : riseAway(element)
    animation.onfinish = () => {
      const index = active.indexOf(element)
      if (index >= 0) {
        active.splice(index, 1)
      }
      element.remove()
    }
  }

  /** 组件销毁时把还在飞的浮字连同动画一起收掉 */
  function dispose(): void {
    active.forEach(remove)
    active.length = 0
  }

  return { spawn, dispose }
}
