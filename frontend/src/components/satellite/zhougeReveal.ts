import * as THREE from 'three'
import { easeOutBack, easeOutCubic } from './motion'
import { createCanvasTexture, createPointCloud, RENDER_ORDER, type PointCloud } from './sceneParts'

const FLY_IN_MS = 750
const HOLD_MS = 2800
const FLY_OUT_MS = 650
const CONFETTI_COUNT = 260
const CONFETTI_LIFE_MS = 2400
const CONFETTI_GRAVITY = 0.00018

/**
 * 周哥出场：脸从 MAA 卫星里转着飞到镜头前，炸一把彩纸，停一会儿再缩回 MAA。
 * 全程压在所有东西上面，不参与深度测试。
 */
export class ZhougeReveal {
  private readonly scene: THREE.Scene
  private readonly sprite: THREE.Sprite
  private readonly confetti: PointCloud
  private readonly velocities = new Float32Array(CONFETTI_COUNT * 3)
  private readonly startTime: number
  private readonly flyOutFrom = new THREE.Vector3()
  private readonly confettiOrigin = new THREE.Vector3()
  private confettiAt: number | null = null
  private flyOutAt: number | null = null
  private flyOutFromScale = 0

  constructor(scene: THREE.Scene, faceCanvas: HTMLCanvasElement, startTime: number) {
    this.scene = scene
    this.startTime = startTime

    this.sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: createCanvasTexture(faceCanvas),
        transparent: true,
        depthTest: false,
        depthWrite: false,
      })
    )
    this.sprite.renderOrder = RENDER_ORDER.overlay + 1
    this.sprite.scale.setScalar(0.001)

    this.confetti = createPointCloud(CONFETTI_COUNT, RENDER_ORDER.overlay)
    this.confetti.points.material.depthTest = false
    this.confetti.points.material.blending = THREE.NormalBlending

    scene.add(this.sprite, this.confetti.points)
  }

  /** 已经在缩回去了就不再响应 */
  dismiss(time: number): void {
    if (this.flyOutAt === null && time - this.startTime > FLY_IN_MS * 0.6) {
      this.startFlyOut(time)
    }
  }

  /**
   * 推进到 time。from 是 MAA 卫星当前位置，stage 是镜头前的停靠点，faceSize 是停在那里时脸的大小。
   * 返回 true 表示演完了，可以 dispose。
   */
  update(time: number, from: THREE.Vector3, stage: THREE.Vector3, faceSize: number): boolean {
    const elapsed = time - this.startTime
    const material = this.sprite.material

    if (this.flyOutAt === null && elapsed >= FLY_IN_MS + HOLD_MS) {
      this.startFlyOut(time)
    }

    if (this.flyOutAt !== null) {
      const progress = Math.min(1, (time - this.flyOutAt) / FLY_OUT_MS)
      const eased = easeOutCubic(progress)
      this.sprite.position.lerpVectors(this.flyOutFrom, from, eased)
      this.sprite.scale.setScalar(Math.max(0.001, this.flyOutFromScale * (1 - eased)))
      material.rotation = -Math.PI * 2 * eased
    } else if (elapsed < FLY_IN_MS) {
      const progress = Math.max(0, elapsed / FLY_IN_MS)
      this.sprite.position.lerpVectors(from, stage, easeOutCubic(progress))
      this.sprite.scale.setScalar(Math.max(0.001, faceSize * easeOutBack(progress)))
      material.rotation = Math.PI * 4 * easeOutCubic(progress)
    } else {
      // 停在镜头前上下晃、一鼓一鼓的
      const hold = elapsed - FLY_IN_MS
      this.sprite.position.copy(stage)
      this.sprite.position.y += Math.sin(hold * 0.006) * 8
      this.sprite.scale.setScalar(faceSize * (1 + 0.05 * Math.sin(hold * 0.012)))
      material.rotation = Math.sin(hold * 0.004) * 0.14
    }

    if (this.confettiAt === null && elapsed >= FLY_IN_MS * 0.85) {
      this.burstConfetti(time, stage)
    }
    const confettiActive = this.updateConfetti(time)

    return this.flyOutAt !== null && time - this.flyOutAt >= FLY_OUT_MS && !confettiActive
  }

  dispose(): void {
    this.scene.remove(this.sprite, this.confetti.points)
    this.sprite.material.map?.dispose()
    this.sprite.material.dispose()
    this.confetti.points.geometry.dispose()
    this.confetti.points.material.dispose()
  }

  private startFlyOut(time: number): void {
    this.flyOutAt = time
    this.flyOutFrom.copy(this.sprite.position)
    this.flyOutFromScale = this.sprite.scale.x
  }

  private burstConfetti(time: number, origin: THREE.Vector3): void {
    this.confettiAt = time
    this.confettiOrigin.copy(origin)
    const color = new THREE.Color()
    for (let i = 0; i < CONFETTI_COUNT; i++) {
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      const speed = 0.12 + Math.random() * 0.26
      this.velocities.set(
        [
          speed * Math.sin(phi) * Math.cos(theta),
          speed * Math.cos(phi) * 0.8 + 0.12,
          speed * Math.sin(phi) * Math.sin(theta) * 0.5,
        ],
        i * 3
      )
      color.setHSL(Math.random(), 0.9, 0.6)
      this.confetti.colors.set([color.r, color.g, color.b], i * 3)
      this.confetti.sizes[i] = 7 + Math.random() * 7
    }
    this.confetti.commit()
  }

  private updateConfetti(time: number): boolean {
    if (this.confettiAt === null) {
      return true
    }

    const age = time - this.confettiAt
    if (age > CONFETTI_LIFE_MS) {
      this.confetti.points.visible = false
      return false
    }

    // 位置按出发点、初速度和重力直接算，掉帧也不会飞丢
    const { positions, alphas } = this.confetti
    const origin = this.confettiOrigin
    const drop = 0.5 * CONFETTI_GRAVITY * age * age
    const alpha = 1 - Math.pow(age / CONFETTI_LIFE_MS, 2)
    for (let i = 0; i < CONFETTI_COUNT; i++) {
      positions[i * 3] = origin.x + this.velocities[i * 3] * age
      positions[i * 3 + 1] = origin.y + this.velocities[i * 3 + 1] * age - drop
      positions[i * 3 + 2] = origin.z + this.velocities[i * 3 + 2] * age
      alphas[i] = alpha
    }
    this.confetti.commit()
    return true
  }
}
