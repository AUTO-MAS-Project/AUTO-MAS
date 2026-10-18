/**
 * 周哥的脸：把图片放到 `src/assets/easter/zhouge.(png|jpg|jpeg|webp)` 就会用上，
 * 没放的时候画一张戴墨镜的占位脸。用 glob 是为了图片不存在时构建也不报错。
 */
const faceAssets = import.meta.glob<string>('@/assets/easter/zhouge.{png,jpg,jpeg,webp}', {
  eager: true,
  query: '?url',
  import: 'default',
})

const FACE_SIZE = 512

function drawPlaceholderFace(context: CanvasRenderingContext2D): void {
  const center = FACE_SIZE / 2
  const radius = FACE_SIZE * 0.44

  const skin = context.createRadialGradient(
    center - radius * 0.3,
    center - radius * 0.35,
    radius * 0.1,
    center,
    center,
    radius
  )
  skin.addColorStop(0, '#ffe59a')
  skin.addColorStop(1, '#f5b23c')
  context.fillStyle = skin
  context.beginPath()
  context.arc(center, center, radius, 0, Math.PI * 2)
  context.fill()

  // 墨镜
  context.fillStyle = '#16181d'
  const lensY = center - radius * 0.18
  for (const side of [-1, 1]) {
    context.beginPath()
    context.roundRect(
      center + side * radius * 0.47 - radius * 0.36,
      lensY,
      radius * 0.72,
      radius * 0.4,
      28
    )
    context.fill()
  }
  context.fillRect(center - radius * 0.14, lensY + radius * 0.08, radius * 0.28, radius * 0.08)
  context.fillStyle = 'rgba(255, 255, 255, 0.55)'
  for (const side of [-1, 1]) {
    context.beginPath()
    context.ellipse(
      center + side * radius * 0.47 - radius * 0.14,
      lensY + radius * 0.12,
      radius * 0.1,
      radius * 0.05,
      -0.5,
      0,
      Math.PI * 2
    )
    context.fill()
  }

  // 歪嘴笑
  context.strokeStyle = '#6b3410'
  context.lineWidth = 16
  context.lineCap = 'round'
  context.beginPath()
  context.moveTo(center - radius * 0.3, center + radius * 0.42)
  context.quadraticCurveTo(
    center + radius * 0.05,
    center + radius * 0.62,
    center + radius * 0.38,
    center + radius * 0.3
  )
  context.stroke()
}

/** 把图片裁成圆、加一圈描边，画成一块正方形画布 */
function drawFramedPhoto(context: CanvasRenderingContext2D, image: HTMLImageElement): void {
  const center = FACE_SIZE / 2
  const radius = FACE_SIZE * 0.46
  context.save()
  context.beginPath()
  context.arc(center, center, radius, 0, Math.PI * 2)
  context.clip()
  const scale = Math.max((radius * 2) / image.width, (radius * 2) / image.height)
  const width = image.width * scale
  const height = image.height * scale
  context.drawImage(image, center - width / 2, center - height / 2, width, height)
  context.restore()
}

function drawRim(context: CanvasRenderingContext2D): void {
  const center = FACE_SIZE / 2
  context.lineWidth = 14
  context.strokeStyle = '#ffffff'
  context.beginPath()
  context.arc(center, center, FACE_SIZE * 0.46, 0, Math.PI * 2)
  context.stroke()
}

/** 画好周哥的脸；有图用图，图加载失败也退回占位脸 */
export async function createZhougeFaceCanvas(): Promise<HTMLCanvasElement> {
  const canvas = document.createElement('canvas')
  canvas.width = FACE_SIZE
  canvas.height = FACE_SIZE
  const context = canvas.getContext('2d')!

  const url = Object.values(faceAssets)[0]
  const image = url
    ? await new Promise<HTMLImageElement | null>(resolve => {
        const img = new Image()
        img.onload = () => resolve(img)
        img.onerror = () => resolve(null)
        img.src = url
      })
    : null

  if (image) {
    drawFramedPhoto(context, image)
  } else {
    drawPlaceholderFace(context)
  }
  drawRim(context)
  return canvas
}
