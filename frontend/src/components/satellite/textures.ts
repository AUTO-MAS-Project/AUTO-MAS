import * as THREE from 'three'

// ==================== 画布贴图 ====================
// 场景里的光晕、冲击波、星云、彩蛋道具都是现画的，不带图片素材。

function drawTexture(
  size: number,
  draw: (ctx: CanvasRenderingContext2D, size: number) => void,
  colored = false
): THREE.CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  draw(canvas.getContext('2d')!, size)
  const texture = new THREE.CanvasTexture(canvas)
  // 带颜色的按 sRGB 解读，颜色才和画的时候一致；纯白的光晕贴图靠材质染色，不用管
  if (colored) texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

export function createGlowTexture(): THREE.CanvasTexture {
  return drawTexture(128, (ctx, size) => {
    const c = size / 2
    const gradient = ctx.createRadialGradient(c, c, 0, c, c, c)
    gradient.addColorStop(0, 'rgba(255, 255, 255, 0.85)')
    gradient.addColorStop(0.15, 'rgba(255, 255, 255, 0.55)')
    gradient.addColorStop(0.35, 'rgba(255, 255, 255, 0.2)')
    gradient.addColorStop(0.6, 'rgba(255, 255, 255, 0.05)')
    gradient.addColorStop(1, 'rgba(255, 255, 255, 0)')
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)
  })
}

/** 冲击波：一圈两侧虚化的细光环，白色，靠材质染成青色或金色 */
export function createShockwaveTexture(): THREE.CanvasTexture {
  return drawTexture(256, (ctx, size) => {
    const c = size / 2
    const gradient = ctx.createRadialGradient(c, c, 0, c, c, c)
    gradient.addColorStop(0, 'rgba(255, 255, 255, 0)')
    gradient.addColorStop(0.78, 'rgba(255, 255, 255, 0)')
    gradient.addColorStop(0.92, 'rgba(255, 255, 255, 0.95)')
    gradient.addColorStop(0.96, 'rgba(255, 255, 255, 0.35)')
    gradient.addColorStop(1, 'rgba(255, 255, 255, 0)')
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)
  })
}

/** 星核背后的光芒：从中心放射、长短粗细不一的光束 */
export function createRaysTexture(): THREE.CanvasTexture {
  return drawTexture(512, (ctx, size) => {
    const c = size / 2
    ctx.translate(c, c)
    ctx.globalCompositeOperation = 'lighter'
    const rays = 56
    for (let i = 0; i < rays; i++) {
      const angle = (i / rays) * Math.PI * 2 + (Math.random() - 0.5) * 0.06
      const length = c * (0.45 + Math.random() * 0.55)
      const width = 2 + Math.random() * 7
      const gradient = ctx.createLinearGradient(0, 0, length, 0)
      gradient.addColorStop(0, 'rgba(255, 255, 255, 0.5)')
      gradient.addColorStop(0.35, 'rgba(255, 255, 255, 0.16)')
      gradient.addColorStop(1, 'rgba(255, 255, 255, 0)')
      ctx.save()
      ctx.rotate(angle)
      ctx.fillStyle = gradient
      ctx.beginPath()
      ctx.moveTo(0, -width * 0.15)
      ctx.lineTo(length, -width / 2)
      ctx.lineTo(length, width / 2)
      ctx.lineTo(0, width * 0.15)
      ctx.closePath()
      ctx.fill()
      ctx.restore()
    }
  })
}

/** 一团星云：几坨偏移的柔光叠在一起，色相在 hue 附近浮动 */
export function createNebulaTexture(hue: number): THREE.CanvasTexture {
  return drawTexture(
    256,
    (ctx, size) => {
      ctx.globalCompositeOperation = 'lighter'
      for (let i = 0; i < 9; i++) {
        const x = size * (0.3 + Math.random() * 0.4)
        const y = size * (0.3 + Math.random() * 0.4)
        const radius = size * (0.18 + Math.random() * 0.3)
        const h = (hue + (Math.random() - 0.5) * 40 + 360) % 360
        const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius)
        gradient.addColorStop(0, `hsla(${h}, 80%, 62%, 0.22)`)
        gradient.addColorStop(0.5, `hsla(${h}, 80%, 52%, 0.08)`)
        gradient.addColorStop(1, `hsla(${h}, 80%, 45%, 0)`)
        ctx.fillStyle = gradient
        ctx.fillRect(0, 0, size, size)
      }
    },
    true
  )
}

export function createHeartTexture(): THREE.CanvasTexture {
  return drawTexture(
    128,
    (ctx, size) => {
      const s = size / 128
      ctx.shadowColor = 'rgba(255, 90, 140, 0.9)'
      ctx.shadowBlur = 14 * s
      const gradient = ctx.createLinearGradient(0, 20 * s, 0, 110 * s)
      gradient.addColorStop(0, '#ff9ec4')
      gradient.addColorStop(1, '#ff3d7f')
      ctx.fillStyle = gradient
      ctx.beginPath()
      ctx.moveTo(64 * s, 104 * s)
      ctx.bezierCurveTo(14 * s, 70 * s, 14 * s, 30 * s, 40 * s, 26 * s)
      ctx.bezierCurveTo(54 * s, 24 * s, 62 * s, 34 * s, 64 * s, 42 * s)
      ctx.bezierCurveTo(66 * s, 34 * s, 74 * s, 24 * s, 88 * s, 26 * s)
      ctx.bezierCurveTo(114 * s, 30 * s, 114 * s, 70 * s, 64 * s, 104 * s)
      ctx.fill()
    },
    true
  )
}

/** 一颗四角星形的结晶，648 下雨用 */
export function createCrystalTexture(): THREE.CanvasTexture {
  return drawTexture(
    128,
    (ctx, size) => {
      const c = size / 2
      ctx.shadowColor = 'rgba(255, 220, 120, 0.95)'
      ctx.shadowBlur = 16
      const gradient = ctx.createLinearGradient(c - 40, c - 40, c + 40, c + 40)
      gradient.addColorStop(0, '#fff7d1')
      gradient.addColorStop(0.45, '#ffd36b')
      gradient.addColorStop(1, '#7fd8ff')
      ctx.fillStyle = gradient
      ctx.beginPath()
      for (let i = 0; i < 8; i++) {
        const radius = i % 2 === 0 ? 50 : 13
        const angle = (i / 8) * Math.PI * 2 - Math.PI / 2
        ctx.lineTo(c + Math.cos(angle) * radius, c + Math.sin(angle) * radius)
      }
      ctx.closePath()
      ctx.fill()
    },
    true
  )
}
