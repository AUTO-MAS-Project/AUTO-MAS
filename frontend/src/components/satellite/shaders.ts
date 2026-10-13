/** 星核外壳：边缘发光的菲涅尔球，叠一层缓慢上移的全息扫描线 */
export const CORE_SHELL_SHADER = {
  vertex: /* glsl */ `
    varying vec3 vNormal;
    varying vec3 vViewDir;
    varying float vHeight;
    void main() {
      vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
      vNormal = normalize(normalMatrix * normal);
      vViewDir = normalize(-mvPosition.xyz);
      vHeight = position.y;
      gl_Position = projectionMatrix * mvPosition;
    }
  `,
  fragment: /* glsl */ `
    uniform vec3 uColor;
    uniform float uIntensity;
    uniform float uTime;
    varying vec3 vNormal;
    varying vec3 vViewDir;
    varying float vHeight;
    void main() {
      float facing = max(dot(normalize(vNormal), normalize(vViewDir)), 0.0);
      float rim = pow(1.0 - facing, 2.4);
      float scan = smoothstep(0.82, 1.0, fract(vHeight * 0.09 - uTime * 0.00035));
      float alpha = (rim * 0.9 + scan * 0.18 * (0.35 + rim)) * uIntensity;
      gl_FragColor = vec4(uColor * alpha, alpha);
    }
  `,
}

/** 轨道线：离镜头近的半圈亮、远的半圈暗，再叠一串沿轨道流动的光点 */
export const ORBIT_SHADER = {
  vertex: /* glsl */ `
    attribute float aAngle;
    uniform float uRadius;
    uniform float uCenterDepth;
    varying float vFront;
    varying float vAngle;
    void main() {
      vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
      vFront = clamp((mvPosition.z - uCenterDepth) / uRadius * 0.5 + 0.5, 0.0, 1.0);
      vAngle = aAngle;
      gl_Position = projectionMatrix * mvPosition;
    }
  `,
  fragment: /* glsl */ `
    uniform vec3 uColor;
    uniform float uOpacity;
    uniform float uTime;
    uniform float uFlow;
    varying float vFront;
    varying float vAngle;
    void main() {
      float base = mix(0.16, 0.62, vFront);
      float dash = 0.72 + 0.28 * sin(vAngle * 36.0 - uTime * 0.0025 * uFlow);
      gl_FragColor = vec4(uColor, base * dash * uOpacity);
    }
  `,
}

/** 圆点粒子：星空、星核漩涡、彗尾、彩纸共用，每个点自带颜色、透明度和大小 */
export const POINTS_SHADER = {
  vertex: /* glsl */ `
    attribute float aSize;
    attribute float aAlpha;
    attribute vec3 aColor;
    attribute float aPhase;
    uniform float uTime;
    uniform float uPixelRatio;
    uniform float uTwinkle;
    varying float vAlpha;
    varying vec3 vColor;
    void main() {
      vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
      float twinkle = mix(1.0, 0.55 + 0.45 * sin(uTime * 0.002 + aPhase), uTwinkle);
      vAlpha = aAlpha * twinkle;
      vColor = aColor;
      gl_PointSize = aSize * uPixelRatio * (1000.0 / -mvPosition.z);
      gl_Position = projectionMatrix * mvPosition;
    }
  `,
  fragment: /* glsl */ `
    varying float vAlpha;
    varying vec3 vColor;
    void main() {
      vec2 offset = gl_PointCoord - vec2(0.5);
      float falloff = smoothstep(0.5, 0.0, length(offset));
      float alpha = vAlpha * falloff;
      if (alpha < 0.003) discard;
      gl_FragColor = vec4(vColor * alpha, alpha);
    }
  `,
}
