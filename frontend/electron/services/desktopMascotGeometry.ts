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

/** 角色可跨相邻屏幕接缝，但不能进入工作区之间的空洞或桌面外侧。 */
export function isMascotVisible(position: Point, size: Size, areas: Rectangle[]): boolean {
  const right = position.x + size.width
  const bottom = position.y + size.height
  const edges = [position.x, right]
  for (const area of areas) {
    for (const edge of [area.x, area.x + area.width]) {
      if (edge > position.x && edge < right) edges.push(edge)
    }
  }
  edges.sort((a, b) => a - b)
  for (let index = 1; index < edges.length; index++) {
    if (edges[index] === edges[index - 1]) continue
    const x = (edges[index - 1] + edges[index]) / 2
    const column = areas
      .filter(area => area.x <= x && x < area.x + area.width)
      .sort((a, b) => a.y - b.y)
    let covered = position.y
    for (const area of column) {
      if (area.y > covered) break
      covered = Math.max(covered, area.y + area.height)
      if (covered >= bottom) break
    }
    if (covered < bottom) return false
  }
  return true
}

function clampMascotPosition(position: Point, size: Size, areas: Rectangle[]): Point {
  if (isMascotVisible(position, size, areas)) return position
  const xs = new Set([position.x])
  const ys = new Set([position.y])
  for (const area of areas) {
    for (const edge of [area.x, area.x + area.width]) {
      xs.add(edge)
      xs.add(edge - size.width)
    }
    for (const edge of [area.y, area.y + area.height]) {
      ys.add(edge)
      ys.add(edge - size.height)
    }
  }
  let nearest = position
  let distance = Infinity
  for (const x of xs) {
    for (const y of ys) {
      const candidateDistance = (x - position.x) ** 2 + (y - position.y) ** 2
      if (candidateDistance < distance && isMascotVisible({ x, y }, size, areas)) {
        nearest = { x, y }
        distance = candidateDistance
      }
    }
  }
  return nearest
}

/** 约束角色的位置，气泡透明区不参与角色的边界判断。 */
export function getMascotLayout(
  position: Point,
  size: Size,
  area: Rectangle,
  areas: Rectangle[] = [area]
) {
  const { x, y } = clampMascotPosition(position, size, areas)
  const noticeWidth = Math.min(NOTICE_WIDTH, area.width)
  const width = Math.max(size.width, noticeWidth)
  const above = Math.max(0, y - area.y)
  const below = Math.max(0, area.y + area.height - y - size.height)
  const noticeBelow = above < NOTICE_HEIGHT && below > above
  const noticeHeight = Math.min(NOTICE_HEIGHT, noticeBelow ? below : above)
  const height = size.height + noticeHeight
  const preferredLeft = Math.max(
    area.x,
    Math.min(x - (width - size.width) / 2, area.x + area.width - width)
  )
  const left = Math.max(x + size.width - width, Math.min(preferredLeft, x))
  const top = noticeBelow ? y : y - noticeHeight
  return {
    bounds: { x: Math.round(left), y: Math.round(top), width, height },
    offset: { x: Math.round(x - left), y: noticeBelow ? 0 : noticeHeight },
    noticeBelow,
    noticeWidth,
    noticeHeight,
  }
}
