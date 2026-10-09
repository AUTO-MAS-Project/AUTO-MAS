import * as THREE from 'three'
import {
  GoldMeteor,
  PointBurst,
  RainEffect,
  ShootingStar,
  SpriteShower,
  WarpEffect,
  type SceneEffect,
  type ShowerParticle,
} from './effects'
import { createCrystalTexture, createHeartTexture } from './textures'

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

/** 流星多久来一颗（毫秒） */
const METEOR_INTERVAL: readonly [number, number] = [7000, 17000]

/**
 * 场景里「放完就收」的特效调度：出金流星、粒子爆发、道具雨、雨幕、曲速线，以及背景里
 * 偶尔划过的流星。场景每帧调一次 update，放完的自己收掉。
 */
export class FxDirector {
  private readonly scene: THREE.Scene
  private readonly camera: THREE.PerspectiveCamera
  private readonly glowTexture: THREE.Texture
  private readonly raysTexture: THREE.Texture
  private effects: SceneEffect[] = []
  private meteors: ShootingStar[] = []
  private nextMeteorAt = 0

  constructor(
    scene: THREE.Scene,
    camera: THREE.PerspectiveCamera,
    textures: { glow: THREE.Texture; rays: THREE.Texture }
  ) {
    this.scene = scene
    this.camera = camera
    this.glowTexture = textures.glow
    this.raysTexture = textures.rays
  }

  /** 推进所有特效；meteorsEnabled 为假时不再放新流星，已经在飞的放完 */
  update(time: number, meteorsEnabled: boolean): void {
    this.effects = this.effects.filter(effect => {
      if (!effect.update(time)) return true
      effect.dispose()
      return false
    })

    this.meteors = this.meteors.filter(meteor => {
      if (!meteor.update(time)) return true
      meteor.dispose()
      return false
    })
    if (meteorsEnabled && time >= this.nextMeteorAt) {
      if (this.nextMeteorAt > 0) {
        this.meteors.push(new ShootingStar(this.camera, this.glowTexture, time))
      }
      this.nextMeteorAt = time + randomBetween(...METEOR_INTERVAL)
    }
  }

  clear(): void {
    for (const effect of [...this.effects, ...this.meteors]) {
      effect.dispose()
    }
    this.effects = []
    this.meteors = []
  }

  /**
   * 指针附近有流星就接住它：在头部炸一小撮星屑，返回它在世界坐标里的位置。
   * project 把世界坐标换成容器像素，判定半径 40 像素——流星飞得快，判得宽一点才点得中。
   */
  catchMeteor(
    pointer: { x: number; y: number },
    project: (world: THREE.Vector3) => { x: number; y: number },
    time: number,
    pixelRatio: number
  ): THREE.Vector3 | null {
    const head = new THREE.Vector3()
    for (const meteor of this.meteors) {
      meteor.worldHead(head)
      const screen = project(head)
      if (Math.hypot(screen.x - pointer.x, screen.y - pointer.y) > 40) continue

      meteor.catch()
      this.sparkle(head, time, pixelRatio, 0xdff4ff, 90)
      return head
    }
    return null
  }

  sparkle(at: THREE.Vector3, time: number, pixelRatio: number, color: number, count = 140): void {
    this.effects.push(
      new PointBurst(this.scene, {
        origin: at,
        count,
        speed: [0.05, 0.22],
        gravity: 0.00008,
        life: 1300,
        size: [4, 9],
        color: (_, out) => out.setHex(color).offsetHSL(0, 0, (Math.random() - 0.5) * 0.2),
        startTime: time,
        pixelRatio,
        overlay: true,
      })
    )
  }

  /** 入场的曲速跃迁 */
  warp(time: number): void {
    this.effects.push(new WarpEffect(this.camera, time))
  }

  /** 暴雨幕 */
  rain(time: number, duration: number): void {
    this.effects.push(new RainEffect(this.camera, time, duration))
  }

  /**
   * 出金：金色流星砸向 getTarget()，砸中时 onImpact 由场景放冲击波和星核闪光，这里补一把金粉；
   * rainbow 为真时金粉换成彩虹色（蔚蓝档案的「出彩」）。
   */
  goldPull(options: {
    time: number
    color: number
    rainbow: boolean
    pixelRatio: number
    getTarget: () => THREE.Vector3
    onImpact: (time: number) => void
  }): void {
    this.effects.push(
      new GoldMeteor(this.scene, {
        camera: this.camera,
        glowTexture: this.glowTexture,
        raysTexture: this.raysTexture,
        color: options.color,
        startTime: options.time,
        getTarget: options.getTarget,
        onImpact: (time, at) => {
          options.onImpact(time)
          this.effects.push(
            new PointBurst(this.scene, {
              origin: at,
              count: 280,
              speed: [0.1, 0.42],
              lift: 0.1,
              gravity: 0.0002,
              life: 1900,
              size: [5, 13],
              color: (_, out) =>
                options.rainbow
                  ? out.setHSL(Math.random(), 0.85, 0.65)
                  : out
                      .setHex(options.color)
                      .offsetHSL((Math.random() - 0.5) * 0.05, 0, (Math.random() - 0.3) * 0.3),
              startTime: time,
              pixelRatio: options.pixelRatio,
              overlay: true,
            })
          )
        },
      })
    )
  }

  /** 648：原石雨，从画面上方斜斜落下 */
  crystalRain(time: number): void {
    const particles = this.spreadParticles(70, index => ({
      offset: [randomBetween(-950, 950), randomBetween(360, 720)],
      velocity: [randomBetween(-0.04, 0.04), -randomBetween(0.22, 0.4)],
      size: randomBetween(24, 46),
      delay: randomBetween(0, 1200),
      life: 2600,
      spin: randomBetween(-0.004, 0.004),
      sway: index % 3 === 0 ? 14 : 0,
    }))
    this.effects.push(
      new SpriteShower(this.scene, {
        texture: createCrystalTexture(),
        particles,
        gravity: 0.00006,
        startTime: time,
        blending: THREE.AdditiveBlending,
      })
    )
  }

  /** 520：爱心从下往上飘 */
  hearts(time: number): void {
    const particles = this.spreadParticles(36, () => ({
      offset: [randomBetween(-760, 760), randomBetween(-460, -330)],
      velocity: [0, randomBetween(0.18, 0.3)],
      size: randomBetween(26, 54),
      delay: randomBetween(0, 1000),
      life: 2800,
      spin: randomBetween(-0.0008, 0.0008),
      sway: randomBetween(12, 30),
    }))
    this.effects.push(
      new SpriteShower(this.scene, {
        texture: createHeartTexture(),
        particles,
        gravity: -0.00002,
        startTime: time,
        blending: THREE.NormalBlending,
      })
    )
  }

  /** 666：三发烟花接连炸开 */
  fireworks(time: number, pixelRatio: number): void {
    const { right, up } = this.cameraAxes()
    for (let i = 0; i < 3; i++) {
      const hue = Math.random()
      const origin = new THREE.Vector3()
        .addScaledVector(right, randomBetween(-520, 520))
        .addScaledVector(up, randomBetween(40, 240))
      this.effects.push(
        new PointBurst(this.scene, {
          origin,
          count: 200,
          speed: [0.16, 0.3],
          gravity: 0.00014,
          life: 1700,
          size: [5, 11],
          color: (_, out) => out.setHSL((hue + (Math.random() - 0.5) * 0.08 + 1) % 1, 0.9, 0.64),
          startTime: time + i * 380,
          pixelRatio,
          overlay: true,
        })
      )
    }
  }

  private cameraAxes(): { right: THREE.Vector3; up: THREE.Vector3 } {
    return {
      right: new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 0),
      up: new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 1),
    }
  }

  /** 按镜头的右、上方向摆一批道具：offset 和 velocity 都是「右、上」两个分量 */
  private spreadParticles(
    count: number,
    make: (index: number) => {
      offset: [number, number]
      velocity: [number, number]
      size: number
      delay: number
      life: number
      spin: number
      sway: number
    }
  ): ShowerParticle[] {
    const { right, up } = this.cameraAxes()
    return Array.from({ length: count }, (_, index) => {
      const item = make(index)
      return {
        position: new THREE.Vector3()
          .addScaledVector(right, item.offset[0])
          .addScaledVector(up, item.offset[1]),
        velocity: new THREE.Vector3()
          .addScaledVector(right, item.velocity[0])
          .addScaledVector(up, item.velocity[1]),
        size: item.size,
        delay: item.delay,
        life: item.life,
        spin: item.spin,
        sway: item.sway,
      }
    })
  }
}
