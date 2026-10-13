import * as THREE from 'three'
import { describe, expect, it } from 'vitest'
import { ORBIT_RINGS, SATELLITE_CONFIG as C } from './config'
import { getRingBasis, getRingPoint } from './motion'

/** 卫星方块半宽：35，加上自转摆动露出的边角 */
const SATELLITE_HALF = 38
/** 卫星边缘离星核中心至少这么远：外壳半径 70，再留一点缝 */
const CORE_KEEP_OUT = C.coreShellRadius + 8
/** 鼠标视差和镜头慢摇（±0.05）能把镜头带到的最远处 */
const YAWS = [-(C.parallaxYaw + 0.05), 0, C.parallaxYaw + 0.05]
const PITCHES = [
  C.cameraElevation - C.parallaxPitch,
  C.cameraElevation,
  C.cameraElevation + C.parallaxPitch,
]
const SAMPLES = 360

/** 照 SatelliteScene.updateCamera 摆镜头 */
function placeCamera(yaw: number, pitch: number): THREE.PerspectiveCamera {
  const camera = new THREE.PerspectiveCamera(C.cameraFov, 2.4, 1, 6000)
  const distance = C.cameraDistance
  camera.position.set(
    distance * Math.sin(yaw) * Math.cos(pitch),
    distance * Math.sin(pitch),
    distance * Math.cos(yaw) * Math.cos(pitch)
  )
  camera.lookAt(0, C.cameraTargetY, 0)
  camera.updateMatrixWorld()
  return camera
}

/** 投影到屏幕，单位换成「星核那么远处的世界单位」，横竖同一把尺；depth 是离镜头的远近 */
function toScreen(camera: THREE.PerspectiveCamera, point: THREE.Vector3) {
  const halfHeight = camera.position.length() * Math.tan(THREE.MathUtils.degToRad(C.cameraFov / 2))
  const ndc = point.clone().project(camera)
  const depth = -point.clone().applyMatrix4(camera.matrixWorldInverse).z
  return {
    x: ndc.x * camera.aspect * halfHeight,
    y: ndc.y * halfHeight,
    halfHeight,
    /** 这个远近上一个世界单位在屏幕上有多大，按星核处为 1 */
    scale: camera.position.length() / depth,
  }
}

function ringPoints(index: number): THREE.Vector3[] {
  const ring = ORBIT_RINGS[index]
  const basis = getRingBasis(ring)
  return Array.from({ length: SAMPLES }, (_, i) => {
    const p = getRingPoint(basis, ring.radius, (i / SAMPLES) * Math.PI * 2)
    return new THREE.Vector3(p.x, p.y, p.z)
  })
}

describe('orbit clearance', () => {
  it('默认视角加视差、慢摇范围内，卫星都绕开星核，不从它前后压过去', () => {
    ORBIT_RINGS.forEach((ring, index) => {
      let closest = Infinity
      for (const yaw of YAWS) {
        for (const pitch of PITCHES) {
          const camera = placeCamera(yaw, pitch)
          const core = toScreen(camera, new THREE.Vector3(0, 0, 0))
          for (const point of ringPoints(index)) {
            const p = toScreen(camera, point)
            const gap = Math.hypot(p.x - core.x, p.y - core.y) - SATELLITE_HALF * p.scale
            closest = Math.min(closest, gap)
          }
        }
      }
      expect(closest, `半径 ${ring.radius} 的轨道离星核太近`).toBeGreaterThanOrEqual(CORE_KEEP_OUT)
    })
  })

  it('默认视角下卫星上下不出画', () => {
    const camera = placeCamera(0, C.cameraElevation)
    ORBIT_RINGS.forEach((ring, index) => {
      for (const point of ringPoints(index)) {
        const p = toScreen(camera, point)
        const reach = Math.abs(p.y) + (C.satelliteSize / 2 + C.satelliteFloatAmplitude) * p.scale
        expect(reach, `半径 ${ring.radius} 的轨道出画`).toBeLessThanOrEqual(p.halfHeight)
      }
    })
  })
})
