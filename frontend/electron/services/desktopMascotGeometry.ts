import type { Point, Rectangle, Size } from 'electron'

const NOTICE_WIDTH = 280
const NOTICE_HEIGHT = 108

export function getMascotSize(source: Size, preferredWidth: number, area: Rectangle): Size {
  const scale = Math.min(
    preferredWidth / source.width,
    (area.width * 0.35) / source.width,
    (area.height * 0.3) / source.height
  )
  return {
    width: Math.max(1, Math.round(source.width * scale)),
    height: Math.max(1, Math.round(source.height * scale)),
  }
}

/** 约束角色的位置，气泡透明区不参与角色的边界判断。 */
export function getMascotLayout(position: Point, size: Size, area: Rectangle) {
  const x = Math.max(area.x, Math.min(position.x, area.x + area.width - size.width))
  const y = Math.max(area.y, Math.min(position.y, area.y + area.height - size.height))
  const width = Math.max(size.width, NOTICE_WIDTH)
  const height = size.height + NOTICE_HEIGHT
  const left = Math.max(area.x, Math.min(x - (width - size.width), area.x + area.width - width))
  const noticeBelow = y - area.y < NOTICE_HEIGHT
  const top = noticeBelow ? y : y - NOTICE_HEIGHT
  return {
    bounds: { x: Math.round(left), y: Math.round(top), width, height },
    offset: { x: Math.round(x - left), y: noticeBelow ? 0 : NOTICE_HEIGHT },
    noticeBelow,
  }
}
