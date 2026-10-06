import * as THREE from 'three'
import { SATELLITE_COLORS, SATELLITE_CONFIG as C } from './config'
import {
  createExplosionFragmentMotion,
  getExplosionEffectProgress,
  getExplosionPhase,
  getFragmentPose,
  SATELLITE_EXPLOSION_CONFIG,
  type ExplosionFragmentMotion,
} from './explosionMotion'
import type { Point3 } from './motion'
import { RENDER_ORDER } from './sceneParts'

interface ExplosionFragment {
  mesh: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>
  motion: ExplosionFragmentMotion
  origin: Point3
}

export interface SatelliteExplosionOptions {
  /** 被炸开的卫星卡片；爆炸期间特效跟着它的位置走 */
  card: THREE.Object3D
  /** 卫星图标原图，按网格切成碎片 */
  source: HTMLCanvasElement
  seed: number
  glowTexture: THREE.Texture
  scene: THREE.Scene
  startTime: number
}

/** 碎片铺满的是图标那一面，比方块本身小一圈 */
const ICON_SIZE = C.satelliteSize * 0.84
const ICON_FACE_Z = C.satelliteDepth / 2 + 0.3

function createFragmentTexture(
  source: HTMLCanvasElement,
  column: number,
  row: number
): THREE.CanvasTexture {
  const columns = SATELLITE_EXPLOSION_CONFIG.fragmentColumns
  const rows = SATELLITE_EXPLOSION_CONFIG.fragmentRows
  const sourceWidth = source.width / columns
  const sourceHeight = source.height / rows
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.ceil(sourceWidth))
  canvas.height = Math.max(1, Math.ceil(sourceHeight))
  const context = canvas.getContext('2d')!
  context.drawImage(
    source,
    column * sourceWidth,
    row * sourceHeight,
    sourceWidth,
    sourceHeight,
    0,
    0,
    canvas.width,
    canvas.height
  )

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.needsUpdate = true
  return texture
}

/** 点卫星的碎裂特效：图标切成 4×4 碎片飞散，带一道闪光和一圈冲击环，最后拼回原样 */
export class SatelliteExplosion {
  private readonly card: THREE.Object3D
  private readonly scene: THREE.Scene
  private readonly startTime: number
  private readonly group = new THREE.Group()
  private readonly fragments: ExplosionFragment[] = []
  private readonly flashSprite: THREE.Sprite
  private readonly ringMesh: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>

  constructor(options: SatelliteExplosionOptions) {
    const { card, source, seed } = options
    this.card = card
    this.scene = options.scene
    this.startTime = options.startTime

    const columns = SATELLITE_EXPLOSION_CONFIG.fragmentColumns
    const rows = SATELLITE_EXPLOSION_CONFIG.fragmentRows
    const fragmentWidth = ICON_SIZE / columns
    const fragmentHeight = ICON_SIZE / rows
    this.group.position.copy(card.position)
    this.group.quaternion.copy(card.quaternion)
    this.group.scale.copy(card.scale)
    // renderOrder 不能设在 Group 上：three 会把它当成子物体的分组序号，碎片就排到所有叠加层
    // （周哥的脸、冲击波）之后去画了。设在每块碎片上。

    for (let row = 0; row < rows; row++) {
      for (let column = 0; column < columns; column++) {
        const material = new THREE.MeshBasicMaterial({
          map: createFragmentTexture(source, column, row),
          transparent: true,
          depthWrite: false,
          side: THREE.DoubleSide,
        })
        const mesh = new THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>(
          new THREE.PlaneGeometry(fragmentWidth, fragmentHeight),
          material
        )
        const origin = {
          x: (column + 0.5 - columns / 2) * fragmentWidth,
          y: (rows / 2 - row - 0.5) * fragmentHeight,
          z: ICON_FACE_Z + 0.1,
        }
        mesh.position.set(origin.x, origin.y, origin.z)
        mesh.renderOrder = RENDER_ORDER.effect
        this.group.add(mesh)
        this.fragments.push({
          mesh,
          motion: createExplosionFragmentMotion(row * columns + column, columns * rows, seed),
          origin,
        })
      }
    }

    this.flashSprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: options.glowTexture,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        color: new THREE.Color(SATELLITE_COLORS.explosionFlash),
        opacity: 1,
      })
    )
    this.flashSprite.position.copy(card.position)
    this.flashSprite.scale.setScalar(C.satelliteSize * 1.2)
    this.flashSprite.renderOrder = RENDER_ORDER.effect

    this.ringMesh = new THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>(
      new THREE.RingGeometry(26, 31, 48),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(SATELLITE_COLORS.explosionRing),
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide,
        opacity: 0.9,
      })
    )
    this.ringMesh.position.copy(card.position)
    this.ringMesh.quaternion.copy(card.quaternion)
    this.ringMesh.scale.setScalar(0.2)
    this.ringMesh.renderOrder = RENDER_ORDER.effect

    this.scene.add(this.group, this.flashSprite, this.ringMesh)
  }

  /** 推进到 time 时刻；返回 true 表示已经放完、可以 dispose */
  update(time: number): boolean {
    const elapsed = Math.max(0, time - this.startTime)

    this.group.position.copy(this.card.position)
    this.group.quaternion.copy(this.card.quaternion)
    this.flashSprite.position.copy(this.card.position)
    this.ringMesh.position.copy(this.card.position)
    this.ringMesh.quaternion.copy(this.card.quaternion)

    for (const { mesh, motion, origin } of this.fragments) {
      const pose = getFragmentPose(motion, origin, elapsed)
      mesh.position.set(pose.x, pose.y, pose.z)
      mesh.rotation.set(pose.rotationX, pose.rotationY, pose.rotationZ)
      mesh.material.opacity = pose.opacity
    }

    const flashProgress = getExplosionEffectProgress(
      elapsed,
      SATELLITE_EXPLOSION_CONFIG.flashDuration
    )
    this.flashSprite.material.opacity = 1 - flashProgress
    this.flashSprite.scale.setScalar(C.satelliteSize * (1.2 + flashProgress * 0.8))

    const ringProgress = getExplosionEffectProgress(
      elapsed,
      SATELLITE_EXPLOSION_CONFIG.ringDuration
    )
    this.ringMesh.material.opacity = (1 - ringProgress) * 0.9
    this.ringMesh.scale.setScalar(0.2 + ringProgress * 1.35)

    return getExplosionPhase(elapsed).complete
  }

  dispose(): void {
    this.scene.remove(this.group, this.flashSprite, this.ringMesh)

    for (const { mesh } of this.fragments) {
      mesh.geometry.dispose()
      mesh.material.map?.dispose()
      mesh.material.dispose()
    }
    this.flashSprite.material.dispose()
    this.ringMesh.geometry.dispose()
    this.ringMesh.material.dispose()
    this.group.clear()
  }
}
