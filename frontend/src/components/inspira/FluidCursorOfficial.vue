<template>
  <div :class="['fluid-cursor', props.class]" aria-hidden="true">
    <canvas id="fluid" ref="canvasRef" class="fluid-cursor__canvas" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch, withDefaults } from 'vue'

interface FluidCursorProps {
  simResolution?: number
  dyeResolution?: number
  captureResolution?: number
  densityDissipation?: number
  velocityDissipation?: number
  pressure?: number
  pressureIterations?: number
  curl?: number
  splatRadius?: number
  splatForce?: number
  shading?: boolean
  colorUpdateSpeed?: number
  backColor?: { r: number; g: number; b: number }
  transparent?: boolean
  class?: string
}

const props = withDefaults(defineProps<FluidCursorProps>(), {
  simResolution: 128,
  dyeResolution: 1440,
  captureResolution: 512,
  densityDissipation: 3.5,
  velocityDissipation: 2,
  pressure: 0.1,
  pressureIterations: 20,
  curl: 3,
  splatRadius: 0.2,
  splatForce: 6000,
  shading: true,
  colorUpdateSpeed: 10,
  backColor: () => ({ r: 0.5, g: 0, b: 0 }),
  transparent: true,
  class: undefined,
})

interface FluidPointer {
  id: number
  texcoordX: number
  texcoordY: number
  prevTexcoordX: number
  prevTexcoordY: number
  deltaX: number
  deltaY: number
  down: boolean
  moved: boolean
  color: { r: number; g: number; b: number }
}

interface TextureFormat {
  internalFormat: number
  format: number
}

interface Framebuffer {
  texture: WebGLTexture
  fbo: WebGLFramebuffer
  width: number
  height: number
  texelSizeX: number
  texelSizeY: number
}

interface DoubleFramebuffer {
  width: number
  height: number
  texelSizeX: number
  texelSizeY: number
  read: Framebuffer
  write: Framebuffer
  swap(): void
}

type FluidWebGLContext = WebGLRenderingContext | WebGL2RenderingContext
type UniformMap = Record<string, WebGLUniformLocation | null>

const vertexShaderSource = `
  precision highp float;
  attribute vec2 aPosition;
  varying vec2 vUv;
  varying vec2 vL;
  varying vec2 vR;
  varying vec2 vT;
  varying vec2 vB;
  uniform vec2 texelSize;

  void main () {
    vUv = aPosition * 0.5 + 0.5;
    vL = vUv - vec2(texelSize.x, 0.0);
    vR = vUv + vec2(texelSize.x, 0.0);
    vT = vUv + vec2(0.0, texelSize.y);
    vB = vUv - vec2(0.0, texelSize.y);
    gl_Position = vec4(aPosition, 0.0, 1.0);
  }
`

const copyFragmentShaderSource = `
  precision mediump float;
  precision mediump sampler2D;
  varying highp vec2 vUv;
  uniform sampler2D uTexture;

  void main () {
    gl_FragColor = texture2D(uTexture, vUv);
  }
`

const clearFragmentShaderSource = `
  precision mediump float;
  precision mediump sampler2D;
  varying highp vec2 vUv;
  uniform sampler2D uTexture;
  uniform float value;

  void main () {
    gl_FragColor = value * texture2D(uTexture, vUv);
  }
`

const splatFragmentShaderSource = `
  precision highp float;
  precision highp sampler2D;
  varying vec2 vUv;
  uniform sampler2D uTarget;
  uniform float aspectRatio;
  uniform vec3 color;
  uniform vec2 point;
  uniform float radius;

  void main () {
    vec2 p = vUv - point.xy;
    p.x *= aspectRatio;
    vec3 splat = exp(-dot(p, p) / radius) * color;
    vec3 base = texture2D(uTarget, vUv).xyz;
    gl_FragColor = vec4(base + splat, 1.0);
  }
`

const advectionFragmentShaderSource = `
  precision highp float;
  precision highp sampler2D;
  varying vec2 vUv;
  uniform sampler2D uVelocity;
  uniform sampler2D uSource;
  uniform vec2 texelSize;
  uniform vec2 dyeTexelSize;
  uniform float dt;
  uniform float dissipation;

  vec4 bilerp (sampler2D sam, vec2 uv, vec2 tsize) {
    vec2 st = uv / tsize - 0.5;
    vec2 iuv = floor(st);
    vec2 fuv = fract(st);

    vec4 a = texture2D(sam, (iuv + vec2(0.5, 0.5)) * tsize);
    vec4 b = texture2D(sam, (iuv + vec2(1.5, 0.5)) * tsize);
    vec4 c = texture2D(sam, (iuv + vec2(0.5, 1.5)) * tsize);
    vec4 d = texture2D(sam, (iuv + vec2(1.5, 1.5)) * tsize);

    return mix(mix(a, b, fuv.x), mix(c, d, fuv.x), fuv.y);
  }

  void main () {
    #ifdef MANUAL_FILTERING
      vec2 coord = vUv - dt * bilerp(uVelocity, vUv, texelSize).xy * texelSize;
      vec4 result = bilerp(uSource, coord, dyeTexelSize);
    #else
      vec2 coord = vUv - dt * texture2D(uVelocity, vUv).xy * texelSize;
      vec4 result = texture2D(uSource, coord);
    #endif
    float decay = 1.0 + dissipation * dt;
    gl_FragColor = result / decay;
  }
`

const divergenceFragmentShaderSource = `
  precision mediump float;
  precision mediump sampler2D;
  varying highp vec2 vUv;
  varying highp vec2 vL;
  varying highp vec2 vR;
  varying highp vec2 vT;
  varying highp vec2 vB;
  uniform sampler2D uVelocity;

  void main () {
    float L = texture2D(uVelocity, vL).x;
    float R = texture2D(uVelocity, vR).x;
    float T = texture2D(uVelocity, vT).y;
    float B = texture2D(uVelocity, vB).y;

    vec2 C = texture2D(uVelocity, vUv).xy;
    if (vL.x < 0.0) { L = -C.x; }
    if (vR.x > 1.0) { R = -C.x; }
    if (vT.y > 1.0) { T = -C.y; }
    if (vB.y < 0.0) { B = -C.y; }

    float div = 0.5 * (R - L + T - B);
    gl_FragColor = vec4(div, 0.0, 0.0, 1.0);
  }
`

const curlFragmentShaderSource = `
  precision mediump float;
  precision mediump sampler2D;
  varying highp vec2 vUv;
  varying highp vec2 vL;
  varying highp vec2 vR;
  varying highp vec2 vT;
  varying highp vec2 vB;
  uniform sampler2D uVelocity;

  void main () {
    float L = texture2D(uVelocity, vL).y;
    float R = texture2D(uVelocity, vR).y;
    float T = texture2D(uVelocity, vT).x;
    float B = texture2D(uVelocity, vB).x;
    float vorticity = R - L - T + B;
    gl_FragColor = vec4(0.5 * vorticity, 0.0, 0.0, 1.0);
  }
`

const vorticityFragmentShaderSource = `
  precision highp float;
  precision highp sampler2D;
  varying vec2 vUv;
  varying vec2 vL;
  varying vec2 vR;
  varying vec2 vT;
  varying vec2 vB;
  uniform sampler2D uVelocity;
  uniform sampler2D uCurl;
  uniform float curl;
  uniform float dt;

  void main () {
    float L = texture2D(uCurl, vL).x;
    float R = texture2D(uCurl, vR).x;
    float T = texture2D(uCurl, vT).x;
    float B = texture2D(uCurl, vB).x;
    float C = texture2D(uCurl, vUv).x;

    vec2 force = 0.5 * vec2(abs(T) - abs(B), abs(R) - abs(L));
    force /= length(force) + 0.0001;
    force *= curl * C;
    force.y *= -1.0;

    vec2 velocity = texture2D(uVelocity, vUv).xy;
    velocity += force * dt;
    velocity = min(max(velocity, -1000.0), 1000.0);
    gl_FragColor = vec4(velocity, 0.0, 1.0);
  }
`

const pressureFragmentShaderSource = `
  precision mediump float;
  precision mediump sampler2D;
  varying highp vec2 vUv;
  varying highp vec2 vL;
  varying highp vec2 vR;
  varying highp vec2 vT;
  varying highp vec2 vB;
  uniform sampler2D uPressure;
  uniform sampler2D uDivergence;

  void main () {
    float L = texture2D(uPressure, vL).x;
    float R = texture2D(uPressure, vR).x;
    float T = texture2D(uPressure, vT).x;
    float B = texture2D(uPressure, vB).x;
    float divergence = texture2D(uDivergence, vUv).x;
    float pressure = (L + R + B + T - divergence) * 0.25;
    gl_FragColor = vec4(pressure, 0.0, 0.0, 1.0);
  }
`

const gradientSubtractFragmentShaderSource = `
  precision mediump float;
  precision mediump sampler2D;
  varying highp vec2 vUv;
  varying highp vec2 vL;
  varying highp vec2 vR;
  varying highp vec2 vT;
  varying highp vec2 vB;
  uniform sampler2D uPressure;
  uniform sampler2D uVelocity;

  void main () {
    float L = texture2D(uPressure, vL).x;
    float R = texture2D(uPressure, vR).x;
    float T = texture2D(uPressure, vT).x;
    float B = texture2D(uPressure, vB).x;
    vec2 velocity = texture2D(uVelocity, vUv).xy;
    velocity.xy -= vec2(R - L, T - B);
    gl_FragColor = vec4(velocity, 0.0, 1.0);
  }
`

const displayFragmentShaderSource = `
  precision highp float;
  precision highp sampler2D;
  varying vec2 vUv;
  varying vec2 vL;
  varying vec2 vR;
  varying vec2 vT;
  varying vec2 vB;
  uniform sampler2D uTexture;
  uniform sampler2D uDithering;
  uniform vec2 ditherScale;
  uniform vec2 texelSize;

  vec3 linearToGamma (vec3 color) {
    color = max(color, vec3(0));
    return max(1.055 * pow(color, vec3(0.416666667)) - 0.055, vec3(0));
  }

  void main () {
    vec3 c = texture2D(uTexture, vUv).rgb;
    #ifdef SHADING
      vec3 lc = texture2D(uTexture, vL).rgb;
      vec3 rc = texture2D(uTexture, vR).rgb;
      vec3 tc = texture2D(uTexture, vT).rgb;
      vec3 bc = texture2D(uTexture, vB).rgb;

      float dx = length(rc) - length(lc);
      float dy = length(tc) - length(bc);

      vec3 normal = normalize(vec3(dx, dy, length(texelSize)));
      vec3 light = vec3(0.0, 0.0, 1.0);

      float diffuse = clamp(dot(normal, light) + 0.7, 0.7, 1.0);
      c *= diffuse;
    #endif

    float alpha = max(c.r, max(c.g, c.b));
    gl_FragColor = vec4(c, alpha);
  }
`

const canvasRef = ref<HTMLCanvasElement | null>(null)
let disposeFluidCursor: (() => void) | null = null

function createPointer(): FluidPointer {
  return {
    id: -1,
    texcoordX: 0,
    texcoordY: 0,
    prevTexcoordX: 0,
    prevTexcoordY: 0,
    deltaX: 0,
    deltaY: 0,
    down: false,
    moved: false,
    color: { r: 0, g: 0, b: 0 },
  }
}

onMounted(() => {
  const canvasElement = canvasRef.value
  if (!canvasElement) {
    return
  }
  const canvas = canvasElement

  const pointers = [createPointer()]
  const config = {
    SIM_RESOLUTION: props.simResolution,
    DYE_RESOLUTION: props.dyeResolution,
    CAPTURE_RESOLUTION: props.captureResolution,
    DENSITY_DISSIPATION: props.densityDissipation,
    VELOCITY_DISSIPATION: props.velocityDissipation,
    PRESSURE: props.pressure,
    PRESSURE_ITERATIONS: props.pressureIterations,
    CURL: props.curl,
    SPLAT_RADIUS: props.splatRadius,
    SPLAT_FORCE: props.splatForce,
    SHADING: props.shading,
    COLOR_UPDATE_SPEED: props.colorUpdateSpeed,
    PAUSED: false,
    BACK_COLOR: props.backColor,
    TRANSPARENT: props.transparent,
  }

  const contextAttributes: WebGLContextAttributes = {
    alpha: true,
    depth: false,
    stencil: false,
    antialias: false,
    preserveDrawingBuffer: false,
  }

  const context = (canvas.getContext('webgl2', contextAttributes) ||
    canvas.getContext('webgl', contextAttributes) ||
    canvas.getContext('experimental-webgl', contextAttributes)) as FluidWebGLContext | null

  if (!context) {
    return
  }
  const gl: FluidWebGLContext = context

  const isWebGL2 = 'drawBuffers' in gl
  const webgl2 = isWebGL2 ? (gl as WebGL2RenderingContext) : null
  if (isWebGL2) {
    // WebGL2 needs this extension enabled before floating-point color
    // attachments such as RGBA16F/RG16F/R16F can be used by the simulation.
    gl.getExtension('EXT_color_buffer_float')
  }
  const halfFloatExtension = isWebGL2
    ? null
    : (gl.getExtension('OES_texture_half_float') as OES_texture_half_float | null)
  const supportLinearFiltering = isWebGL2
    ? Boolean(gl.getExtension('OES_texture_float_linear'))
    : Boolean(gl.getExtension('OES_texture_half_float_linear'))

  gl.clearColor(0, 0, 0, 1)

  const halfFloatTexType = isWebGL2
    ? (webgl2?.HALF_FLOAT ?? 0)
    : (halfFloatExtension?.HALF_FLOAT_OES ?? 0)
  if (!halfFloatTexType) {
    return
  }

  function checkFramebufferFormat(internalFormat: number, format: number, type: number) {
    const texture = gl.createTexture()
    if (!texture) {
      return false
    }

    gl.bindTexture(gl.TEXTURE_2D, texture)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    gl.texImage2D(gl.TEXTURE_2D, 0, internalFormat, 4, 4, 0, format, type, null)

    const framebuffer = gl.createFramebuffer()
    if (!framebuffer) {
      gl.deleteTexture(texture)
      return false
    }

    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer)
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0)
    const complete = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE
    gl.deleteFramebuffer(framebuffer)
    gl.deleteTexture(texture)
    return complete
  }

  function getSupportedFormat(internalFormat: number, format: number): TextureFormat | null {
    if (checkFramebufferFormat(internalFormat, format, halfFloatTexType)) {
      return { internalFormat, format }
    }

    if (!webgl2) {
      return null
    }

    if (internalFormat === webgl2.R16F) {
      return getSupportedFormat(webgl2.RG16F, webgl2.RG)
    }
    if (internalFormat === webgl2.RG16F) {
      return getSupportedFormat(webgl2.RGBA16F, webgl2.RGBA)
    }
    return null
  }

  const rgbaFormat = isWebGL2
    ? getSupportedFormat(webgl2!.RGBA16F, webgl2!.RGBA)
    : getSupportedFormat(gl.RGBA, gl.RGBA)
  const rgFormat = isWebGL2
    ? getSupportedFormat(webgl2!.RG16F, webgl2!.RG)
    : getSupportedFormat(gl.RGBA, gl.RGBA)
  const rFormat = isWebGL2
    ? getSupportedFormat(webgl2!.R16F, webgl2!.RED)
    : getSupportedFormat(gl.RGBA, gl.RGBA)

  if (!rgbaFormat || !rgFormat || !rFormat) {
    return
  }

  if (!supportLinearFiltering) {
    config.DYE_RESOLUTION = 256
    config.SHADING = false
  }

  function hashString(value: string) {
    let hash = 0
    for (let index = 0; index < value.length; index += 1) {
      hash = (hash << 5) - hash + value.charCodeAt(index)
      hash |= 0
    }
    return hash
  }

  function addKeywords(source: string, keywords?: string[] | null) {
    if (!keywords?.length) {
      return source
    }

    return `${keywords.map(keyword => `#define ${keyword}\n`).join('')}${source}`
  }

  function compileShader(type: number, source: string, keywords?: string[] | null) {
    const shader = gl.createShader(type)
    if (!shader) {
      return null
    }

    gl.shaderSource(shader, addKeywords(source, keywords))
    gl.compileShader(shader)
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      gl.deleteShader(shader)
      return null
    }
    return shader
  }

  function createProgram(vertexShader: WebGLShader | null, fragmentShader: WebGLShader | null) {
    if (!vertexShader || !fragmentShader) {
      return null
    }

    const program = gl.createProgram()
    if (!program) {
      return null
    }

    gl.attachShader(program, vertexShader)
    gl.attachShader(program, fragmentShader)
    gl.bindAttribLocation(program, 0, 'aPosition')
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      gl.deleteProgram(program)
      return null
    }
    return program
  }

  function getUniforms(program: WebGLProgram): UniformMap {
    const uniforms: UniformMap = {}
    const uniformCount = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS) as number
    for (let index = 0; index < uniformCount; index += 1) {
      const uniform = gl.getActiveUniform(program, index)
      if (uniform) {
        uniforms[uniform.name] = gl.getUniformLocation(program, uniform.name)
      }
    }
    return uniforms
  }

  class GLProgram {
    program: WebGLProgram | null
    uniforms: UniformMap

    constructor(vertexShader: WebGLShader | null, fragmentShader: WebGLShader | null) {
      this.program = createProgram(vertexShader, fragmentShader)
      this.uniforms = this.program ? getUniforms(this.program) : {}
    }

    bind() {
      if (this.program) {
        gl.useProgram(this.program)
      }
    }

    dispose() {
      if (this.program) {
        gl.deleteProgram(this.program)
      }
      this.program = null
      this.uniforms = {}
    }
  }

  class GLMaterial {
    vertexShader: WebGLShader | null
    fragmentShaderSource: string
    programs: Record<number, WebGLProgram | null> = {}
    activeProgram: WebGLProgram | null = null
    uniforms: UniformMap = {}

    constructor(vertexShader: WebGLShader | null, fragmentShaderSource: string) {
      this.vertexShader = vertexShader
      this.fragmentShaderSource = fragmentShaderSource
    }

    setKeywords(keywords: string[]) {
      const hash = keywords.reduce((value, keyword) => value + hashString(keyword), 0)
      let program = this.programs[hash]
      if (program === undefined) {
        const fragmentShader = compileShader(
          gl.FRAGMENT_SHADER,
          this.fragmentShaderSource,
          keywords
        )
        program = createProgram(this.vertexShader, fragmentShader)
        if (fragmentShader) {
          gl.deleteShader(fragmentShader)
        }
        this.programs[hash] = program
      }

      if (program !== this.activeProgram) {
        if (program) {
          this.uniforms = getUniforms(program)
        }
        this.activeProgram = program
      }
    }

    bind() {
      if (this.activeProgram) {
        gl.useProgram(this.activeProgram)
      }
    }

    dispose() {
      for (const program of Object.values(this.programs)) {
        if (program) {
          gl.deleteProgram(program)
        }
      }
      this.programs = {}
      this.activeProgram = null
      this.uniforms = {}
    }
  }

  const vertexShader = compileShader(gl.VERTEX_SHADER, vertexShaderSource)
  const copyProgram = new GLProgram(
    vertexShader,
    compileShader(gl.FRAGMENT_SHADER, copyFragmentShaderSource)
  )
  const clearProgram = new GLProgram(
    vertexShader,
    compileShader(gl.FRAGMENT_SHADER, clearFragmentShaderSource)
  )
  const splatProgram = new GLProgram(
    vertexShader,
    compileShader(gl.FRAGMENT_SHADER, splatFragmentShaderSource)
  )
  const advectionProgram = new GLProgram(
    vertexShader,
    compileShader(
      gl.FRAGMENT_SHADER,
      advectionFragmentShaderSource,
      supportLinearFiltering ? null : ['MANUAL_FILTERING']
    )
  )
  const divergenceProgram = new GLProgram(
    vertexShader,
    compileShader(gl.FRAGMENT_SHADER, divergenceFragmentShaderSource)
  )
  const curlProgram = new GLProgram(
    vertexShader,
    compileShader(gl.FRAGMENT_SHADER, curlFragmentShaderSource)
  )
  const vorticityProgram = new GLProgram(
    vertexShader,
    compileShader(gl.FRAGMENT_SHADER, vorticityFragmentShaderSource)
  )
  const pressureProgram = new GLProgram(
    vertexShader,
    compileShader(gl.FRAGMENT_SHADER, pressureFragmentShaderSource)
  )
  const gradientProgram = new GLProgram(
    vertexShader,
    compileShader(gl.FRAGMENT_SHADER, gradientSubtractFragmentShaderSource)
  )
  const displayMaterial = new GLMaterial(vertexShader, displayFragmentShaderSource)

  if (
    !vertexShader ||
    !copyProgram.program ||
    !clearProgram.program ||
    !splatProgram.program ||
    !advectionProgram.program ||
    !divergenceProgram.program ||
    !curlProgram.program ||
    !vorticityProgram.program ||
    !pressureProgram.program ||
    !gradientProgram.program
  ) {
    return
  }

  const quadVertexBuffer = gl.createBuffer()
  const quadIndexBuffer = gl.createBuffer()
  if (!quadVertexBuffer || !quadIndexBuffer) {
    return
  }

  gl.bindBuffer(gl.ARRAY_BUFFER, quadVertexBuffer)
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, -1, 1, 1, 1, 1, -1]), gl.STATIC_DRAW)
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, quadIndexBuffer)
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array([0, 1, 2, 0, 2, 3]), gl.STATIC_DRAW)
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0)
  gl.enableVertexAttribArray(0)

  interface RenderTarget {
    width: number
    height: number
    fbo: WebGLFramebuffer | null
  }

  const blit = (target: (Framebuffer & RenderTarget) | null, clear = false) => {
    if (target) {
      gl.viewport(0, 0, target.width, target.height)
      gl.bindFramebuffer(gl.FRAMEBUFFER, target.fbo)
    } else {
      gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight)
      gl.bindFramebuffer(gl.FRAMEBUFFER, null)
    }

    if (clear) {
      gl.clearColor(0, 0, 0, 1)
      gl.clear(gl.COLOR_BUFFER_BIT)
    }
    gl.drawElements(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0)
  }

  function createFramebuffer(
    width: number,
    height: number,
    internalFormat: number,
    format: number,
    type: number,
    filter: number
  ): Framebuffer {
    gl.activeTexture(gl.TEXTURE0)
    const texture = gl.createTexture()
    if (!texture) {
      throw new Error('Unable to create WebGL texture.')
    }

    gl.bindTexture(gl.TEXTURE_2D, texture)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    gl.texImage2D(gl.TEXTURE_2D, 0, internalFormat, width, height, 0, format, type, null)

    const framebuffer = gl.createFramebuffer()
    if (!framebuffer) {
      gl.deleteTexture(texture)
      throw new Error('Unable to create WebGL framebuffer.')
    }

    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer)
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0)
    gl.viewport(0, 0, width, height)
    gl.clear(gl.COLOR_BUFFER_BIT)

    return {
      texture,
      fbo: framebuffer,
      width,
      height,
      texelSizeX: 1 / width,
      texelSizeY: 1 / height,
    }
  }

  function attachFramebuffer(target: Framebuffer, unit: number) {
    gl.activeTexture(gl.TEXTURE0 + unit)
    gl.bindTexture(gl.TEXTURE_2D, target.texture)
    return unit
  }

  function createDoubleFramebuffer(
    width: number,
    height: number,
    internalFormat: number,
    format: number,
    type: number,
    filter: number
  ): DoubleFramebuffer {
    const read = createFramebuffer(width, height, internalFormat, format, type, filter)
    const write = createFramebuffer(width, height, internalFormat, format, type, filter)
    return {
      width,
      height,
      texelSizeX: read.texelSizeX,
      texelSizeY: read.texelSizeY,
      read,
      write,
      swap() {
        const previousRead = this.read
        this.read = this.write
        this.write = previousRead
      },
    }
  }

  function copyFramebuffer(
    source: Framebuffer,
    width: number,
    height: number,
    internalFormat: number,
    format: number,
    type: number,
    filter: number
  ) {
    const target = createFramebuffer(width, height, internalFormat, format, type, filter)
    copyProgram.bind()
    if (copyProgram.uniforms.uTexture) {
      gl.uniform1i(copyProgram.uniforms.uTexture, attachFramebuffer(source, 0))
    }
    blit(target)
    return target
  }

  function destroyFramebuffer(target: Framebuffer | null) {
    if (!target) {
      return
    }
    gl.deleteTexture(target.texture)
    gl.deleteFramebuffer(target.fbo)
  }

  function destroyDoubleFramebuffer(target: DoubleFramebuffer | null) {
    if (!target) {
      return
    }
    destroyFramebuffer(target.read)
    destroyFramebuffer(target.write)
  }

  function resizeDoubleFramebuffer(
    target: DoubleFramebuffer,
    width: number,
    height: number,
    internalFormat: number,
    format: number,
    type: number,
    filter: number
  ) {
    if (target.width === width && target.height === height) {
      return target
    }

    const oldRead = target.read
    const oldWrite = target.write
    target.read = copyFramebuffer(oldRead, width, height, internalFormat, format, type, filter)
    target.write = createFramebuffer(width, height, internalFormat, format, type, filter)
    target.width = width
    target.height = height
    target.texelSizeX = 1 / width
    target.texelSizeY = 1 / height
    destroyFramebuffer(oldRead)
    destroyFramebuffer(oldWrite)
    return target
  }

  let dye: DoubleFramebuffer | null = null
  let velocity: DoubleFramebuffer | null = null
  let curlTarget: Framebuffer | null = null
  let divergenceTarget: Framebuffer | null = null
  let pressure: DoubleFramebuffer | null = null

  function getResolution(resolution: number) {
    const width = gl.drawingBufferWidth
    const height = gl.drawingBufferHeight
    const aspectRatio = width / Math.max(height, 1)
    const correctedAspectRatio = aspectRatio < 1 ? 1 / aspectRatio : aspectRatio
    const correctedResolution = Math.round(resolution)
    const correctedWidth = Math.round(resolution * correctedAspectRatio)
    return width > height
      ? { width: correctedWidth, height: correctedResolution }
      : { width: correctedResolution, height: correctedWidth }
  }

  function initFramebuffers() {
    const simResolution = getResolution(config.SIM_RESOLUTION)
    const dyeResolution = getResolution(config.DYE_RESOLUTION)
    const filter = supportLinearFiltering ? gl.LINEAR : gl.NEAREST

    gl.disable(gl.BLEND)
    dye = dye
      ? resizeDoubleFramebuffer(
          dye,
          dyeResolution.width,
          dyeResolution.height,
          rgbaFormat!.internalFormat,
          rgbaFormat!.format,
          halfFloatTexType,
          filter
        )
      : createDoubleFramebuffer(
          dyeResolution.width,
          dyeResolution.height,
          rgbaFormat!.internalFormat,
          rgbaFormat!.format,
          halfFloatTexType,
          filter
        )
    velocity = velocity
      ? resizeDoubleFramebuffer(
          velocity,
          simResolution.width,
          simResolution.height,
          rgFormat!.internalFormat,
          rgFormat!.format,
          halfFloatTexType,
          filter
        )
      : createDoubleFramebuffer(
          simResolution.width,
          simResolution.height,
          rgFormat!.internalFormat,
          rgFormat!.format,
          halfFloatTexType,
          filter
        )
    destroyFramebuffer(curlTarget)
    destroyFramebuffer(divergenceTarget)
    destroyDoubleFramebuffer(pressure)
    curlTarget = createFramebuffer(
      simResolution.width,
      simResolution.height,
      rFormat!.internalFormat,
      rFormat!.format,
      halfFloatTexType,
      gl.NEAREST
    )
    divergenceTarget = createFramebuffer(
      simResolution.width,
      simResolution.height,
      rFormat!.internalFormat,
      rFormat!.format,
      halfFloatTexType,
      gl.NEAREST
    )
    pressure = createDoubleFramebuffer(
      simResolution.width,
      simResolution.height,
      rFormat!.internalFormat,
      rFormat!.format,
      halfFloatTexType,
      gl.NEAREST
    )
  }

  displayMaterial.setKeywords(config.SHADING ? ['SHADING'] : [])

  function resizeCanvas() {
    const ratio = window.devicePixelRatio || 1
    const width = Math.floor((canvas.clientWidth || window.innerWidth) * ratio)
    const height = Math.floor((canvas.clientHeight || window.innerHeight) * ratio)
    if (canvas.width === width && canvas.height === height) {
      return false
    }
    canvas.width = Math.max(width, 1)
    canvas.height = Math.max(height, 1)
    return true
  }

  resizeCanvas()
  initFramebuffers()

  const blitTarget = (target: Framebuffer | null, clear = false) =>
    blit(target as (Framebuffer & RenderTarget) | null, clear)

  function updateColors(deltaTime: number) {
    colorUpdateTimer += deltaTime * config.COLOR_UPDATE_SPEED
    if (colorUpdateTimer >= 1) {
      colorUpdateTimer = wrap(colorUpdateTimer, 0, 1)
      for (const pointer of pointers) {
        pointer.color = generateColor()
      }
    }
  }

  function applyInputs() {
    for (const pointer of pointers) {
      if (pointer.moved) {
        pointer.moved = false
        splatPointer(pointer)
      }
    }
  }

  function step(deltaTime: number) {
    if (!velocity || !dye || !curlTarget || !divergenceTarget || !pressure) {
      return
    }

    gl.disable(gl.BLEND)
    curlProgram.bind()
    if (curlProgram.uniforms.texelSize) {
      gl.uniform2f(curlProgram.uniforms.texelSize, velocity.texelSizeX, velocity.texelSizeY)
    }
    if (curlProgram.uniforms.uVelocity) {
      gl.uniform1i(curlProgram.uniforms.uVelocity, attachFramebuffer(velocity.read, 0))
    }
    blitTarget(curlTarget)

    vorticityProgram.bind()
    if (vorticityProgram.uniforms.texelSize) {
      gl.uniform2f(vorticityProgram.uniforms.texelSize, velocity.texelSizeX, velocity.texelSizeY)
    }
    if (vorticityProgram.uniforms.uVelocity) {
      gl.uniform1i(vorticityProgram.uniforms.uVelocity, attachFramebuffer(velocity.read, 0))
    }
    if (vorticityProgram.uniforms.uCurl) {
      gl.uniform1i(vorticityProgram.uniforms.uCurl, attachFramebuffer(curlTarget, 1))
    }
    if (vorticityProgram.uniforms.curl) {
      gl.uniform1f(vorticityProgram.uniforms.curl, config.CURL)
    }
    if (vorticityProgram.uniforms.dt) {
      gl.uniform1f(vorticityProgram.uniforms.dt, deltaTime)
    }
    blitTarget(velocity.write)
    velocity.swap()

    divergenceProgram.bind()
    if (divergenceProgram.uniforms.texelSize) {
      gl.uniform2f(divergenceProgram.uniforms.texelSize, velocity.texelSizeX, velocity.texelSizeY)
    }
    if (divergenceProgram.uniforms.uVelocity) {
      gl.uniform1i(divergenceProgram.uniforms.uVelocity, attachFramebuffer(velocity.read, 0))
    }
    blitTarget(divergenceTarget)

    clearProgram.bind()
    if (clearProgram.uniforms.uTexture) {
      gl.uniform1i(clearProgram.uniforms.uTexture, attachFramebuffer(pressure.read, 0))
    }
    if (clearProgram.uniforms.value) {
      gl.uniform1f(clearProgram.uniforms.value, config.PRESSURE)
    }
    blitTarget(pressure.write)
    pressure.swap()

    pressureProgram.bind()
    if (pressureProgram.uniforms.texelSize) {
      gl.uniform2f(pressureProgram.uniforms.texelSize, velocity.texelSizeX, velocity.texelSizeY)
    }
    if (pressureProgram.uniforms.uDivergence) {
      gl.uniform1i(pressureProgram.uniforms.uDivergence, attachFramebuffer(divergenceTarget, 0))
    }
    for (let index = 0; index < config.PRESSURE_ITERATIONS; index += 1) {
      if (pressureProgram.uniforms.uPressure) {
        gl.uniform1i(pressureProgram.uniforms.uPressure, attachFramebuffer(pressure.read, 1))
      }
      blitTarget(pressure.write)
      pressure.swap()
    }

    gradientProgram.bind()
    if (gradientProgram.uniforms.texelSize) {
      gl.uniform2f(gradientProgram.uniforms.texelSize, velocity.texelSizeX, velocity.texelSizeY)
    }
    if (gradientProgram.uniforms.uPressure) {
      gl.uniform1i(gradientProgram.uniforms.uPressure, attachFramebuffer(pressure.read, 0))
    }
    if (gradientProgram.uniforms.uVelocity) {
      gl.uniform1i(gradientProgram.uniforms.uVelocity, attachFramebuffer(velocity.read, 1))
    }
    blitTarget(velocity.write)
    velocity.swap()

    advectionProgram.bind()
    if (advectionProgram.uniforms.texelSize) {
      gl.uniform2f(advectionProgram.uniforms.texelSize, velocity.texelSizeX, velocity.texelSizeY)
    }
    if (!supportLinearFiltering && advectionProgram.uniforms.dyeTexelSize) {
      gl.uniform2f(advectionProgram.uniforms.dyeTexelSize, velocity.texelSizeX, velocity.texelSizeY)
    }
    const velocityTexture = attachFramebuffer(velocity.read, 0)
    if (advectionProgram.uniforms.uVelocity) {
      gl.uniform1i(advectionProgram.uniforms.uVelocity, velocityTexture)
    }
    if (advectionProgram.uniforms.uSource) {
      gl.uniform1i(advectionProgram.uniforms.uSource, velocityTexture)
    }
    if (advectionProgram.uniforms.dt) {
      gl.uniform1f(advectionProgram.uniforms.dt, deltaTime)
    }
    if (advectionProgram.uniforms.dissipation) {
      gl.uniform1f(advectionProgram.uniforms.dissipation, config.VELOCITY_DISSIPATION)
    }
    blitTarget(velocity.write)
    velocity.swap()

    if (!supportLinearFiltering && advectionProgram.uniforms.dyeTexelSize) {
      gl.uniform2f(advectionProgram.uniforms.dyeTexelSize, dye.texelSizeX, dye.texelSizeY)
    }
    if (advectionProgram.uniforms.uVelocity) {
      gl.uniform1i(advectionProgram.uniforms.uVelocity, attachFramebuffer(velocity.read, 0))
    }
    if (advectionProgram.uniforms.uSource) {
      gl.uniform1i(advectionProgram.uniforms.uSource, attachFramebuffer(dye.read, 1))
    }
    if (advectionProgram.uniforms.dissipation) {
      gl.uniform1f(advectionProgram.uniforms.dissipation, config.DENSITY_DISSIPATION)
    }
    blitTarget(dye.write)
    dye.swap()
  }

  function drawDisplay(target: Framebuffer | null) {
    const width = target ? target.width : gl.drawingBufferWidth
    const height = target ? target.height : gl.drawingBufferHeight
    displayMaterial.bind()
    if (config.SHADING && displayMaterial.uniforms.texelSize) {
      gl.uniform2f(displayMaterial.uniforms.texelSize, 1 / width, 1 / height)
    }
    if (displayMaterial.uniforms.uTexture && dye) {
      gl.uniform1i(displayMaterial.uniforms.uTexture, attachFramebuffer(dye.read, 0))
    }
    blitTarget(target)
  }

  function render(target: Framebuffer | null) {
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
    gl.enable(gl.BLEND)
    drawDisplay(target)
  }

  function correctRadius(radius: number) {
    const aspectRatio = canvas.width / Math.max(canvas.height, 1)
    return aspectRatio > 1 ? radius * aspectRatio : radius
  }

  function splat(
    x: number,
    y: number,
    deltaX: number,
    deltaY: number,
    color: { r: number; g: number; b: number }
  ) {
    if (!velocity || !dye) {
      return
    }

    splatProgram.bind()
    if (splatProgram.uniforms.uTarget) {
      gl.uniform1i(splatProgram.uniforms.uTarget, attachFramebuffer(velocity.read, 0))
    }
    if (splatProgram.uniforms.aspectRatio) {
      gl.uniform1f(splatProgram.uniforms.aspectRatio, canvas.width / Math.max(canvas.height, 1))
    }
    if (splatProgram.uniforms.point) {
      gl.uniform2f(splatProgram.uniforms.point, x, y)
    }
    if (splatProgram.uniforms.color) {
      gl.uniform3f(splatProgram.uniforms.color, deltaX, deltaY, 0)
    }
    if (splatProgram.uniforms.radius) {
      gl.uniform1f(splatProgram.uniforms.radius, correctRadius(config.SPLAT_RADIUS / 100))
    }
    blitTarget(velocity.write)
    velocity.swap()

    if (splatProgram.uniforms.uTarget) {
      gl.uniform1i(splatProgram.uniforms.uTarget, attachFramebuffer(dye.read, 0))
    }
    if (splatProgram.uniforms.color) {
      gl.uniform3f(splatProgram.uniforms.color, color.r, color.g, color.b)
    }
    blitTarget(dye.write)
    dye.swap()
  }

  function splatPointer(pointer: FluidPointer) {
    splat(
      pointer.texcoordX,
      pointer.texcoordY,
      pointer.deltaX * config.SPLAT_FORCE,
      pointer.deltaY * config.SPLAT_FORCE,
      pointer.color
    )
  }

  function clickSplat(pointer: FluidPointer) {
    const color = generateColor()
    color.r *= 10
    color.g *= 10
    color.b *= 10
    splat(
      pointer.texcoordX,
      pointer.texcoordY,
      10 * (Math.random() - 0.5),
      30 * (Math.random() - 0.5),
      color
    )
  }

  function setPointerDown(pointer: FluidPointer, id: number, x: number, y: number) {
    pointer.id = id
    pointer.down = true
    pointer.moved = false
    pointer.texcoordX = x / Math.max(canvas.width, 1)
    pointer.texcoordY = 1 - y / Math.max(canvas.height, 1)
    pointer.prevTexcoordX = pointer.texcoordX
    pointer.prevTexcoordY = pointer.texcoordY
    pointer.deltaX = 0
    pointer.deltaY = 0
    pointer.color = generateColor()
  }

  function setPointerMove(
    pointer: FluidPointer,
    x: number,
    y: number,
    color: FluidPointer['color']
  ) {
    pointer.prevTexcoordX = pointer.texcoordX
    pointer.prevTexcoordY = pointer.texcoordY
    pointer.texcoordX = x / Math.max(canvas.width, 1)
    pointer.texcoordY = 1 - y / Math.max(canvas.height, 1)
    pointer.deltaX = correctDeltaX(pointer.texcoordX - pointer.prevTexcoordX)
    pointer.deltaY = correctDeltaY(pointer.texcoordY - pointer.prevTexcoordY)
    pointer.moved = Math.abs(pointer.deltaX) > 0 || Math.abs(pointer.deltaY) > 0
    pointer.color = color
  }

  function setPointerUp(pointer: FluidPointer) {
    pointer.down = false
  }

  function correctDeltaX(delta: number) {
    const aspectRatio = canvas.width / Math.max(canvas.height, 1)
    return aspectRatio < 1 ? delta * aspectRatio : delta
  }

  function correctDeltaY(delta: number) {
    const aspectRatio = canvas.width / Math.max(canvas.height, 1)
    return aspectRatio > 1 ? delta / aspectRatio : delta
  }

  function generateColor() {
    const color = hsvToRgb(Math.random(), 1, 1)
    color.r *= 0.15
    color.g *= 0.15
    color.b *= 0.15
    return color
  }

  function hsvToRgb(hue: number, saturation: number, value: number) {
    const index = Math.floor(hue * 6)
    const fraction = hue * 6 - index
    const p = value * (1 - saturation)
    const q = value * (1 - fraction * saturation)
    const t = value * (1 - (1 - fraction) * saturation)
    let red = 0
    let green = 0
    let blue = 0

    switch (index % 6) {
      case 0:
        red = value
        green = t
        blue = p
        break
      case 1:
        red = q
        green = value
        blue = p
        break
      case 2:
        red = p
        green = value
        blue = t
        break
      case 3:
        red = p
        green = q
        blue = value
        break
      case 4:
        red = t
        green = p
        blue = value
        break
      case 5:
        red = value
        green = p
        blue = q
        break
    }

    return { r: red, g: green, b: blue }
  }

  function wrap(value: number, min: number, max: number) {
    const range = max - min
    return range === 0 ? min : ((value - min) % range) + min
  }

  let lastUpdateTime = Date.now()
  let colorUpdateTimer = 0
  let animationFrameId: number | null = null
  let destroyed = false

  function update() {
    if (destroyed) {
      return
    }

    const deltaTime = Math.min((Date.now() - lastUpdateTime) / 1000, 0.016666)
    lastUpdateTime = Date.now()
    if (resizeCanvas()) {
      initFramebuffers()
    }
    updateColors(deltaTime)
    applyInputs()
    step(deltaTime)
    render(null)
    animationFrameId = window.requestAnimationFrame(update)
  }

  function getScaledPointer(value: number) {
    return Math.floor(value * (window.devicePixelRatio || 1))
  }

  const handleMouseDown = (event: MouseEvent) => {
    const pointer = pointers[0]
    setPointerDown(pointer, -1, getScaledPointer(event.clientX), getScaledPointer(event.clientY))
    clickSplat(pointer)
  }

  const handleFirstMouseMove = (event: MouseEvent) => {
    const pointer = pointers[0]
    const x = getScaledPointer(event.clientX)
    const y = getScaledPointer(event.clientY)
    setPointerMove(pointer, x, y, generateColor())
    document.body.removeEventListener('mousemove', handleFirstMouseMove)
  }

  const handleMouseMove = (event: MouseEvent) => {
    const pointer = pointers[0]
    setPointerMove(
      pointer,
      getScaledPointer(event.clientX),
      getScaledPointer(event.clientY),
      pointer.color
    )
  }

  const handleFirstTouchStart = (event: TouchEvent) => {
    const pointer = pointers[0]
    for (const touch of Array.from(event.targetTouches)) {
      const x = getScaledPointer(touch.clientX)
      const y = getScaledPointer(touch.clientY)
      setPointerDown(pointer, touch.identifier, x, y)
    }
    document.body.removeEventListener('touchstart', handleFirstTouchStart)
  }

  const handleTouchStart = (event: TouchEvent) => {
    const pointer = pointers[0]
    for (const touch of Array.from(event.targetTouches)) {
      setPointerDown(
        pointer,
        touch.identifier,
        getScaledPointer(touch.clientX),
        getScaledPointer(touch.clientY)
      )
    }
  }

  const handleTouchMove = (event: TouchEvent) => {
    const pointer = pointers[0]
    for (const touch of Array.from(event.targetTouches)) {
      setPointerMove(
        pointer,
        getScaledPointer(touch.clientX),
        getScaledPointer(touch.clientY),
        pointer.color
      )
    }
  }

  const handleTouchEnd = () => {
    setPointerUp(pointers[0])
  }

  const stopWatchers = [
    watch(
      () => props.simResolution,
      value => {
        config.SIM_RESOLUTION = value
        initFramebuffers()
      }
    ),
    watch(
      () => props.dyeResolution,
      value => {
        config.DYE_RESOLUTION = value
        initFramebuffers()
      }
    ),
    watch(
      () => props.shading,
      value => {
        config.SHADING = value
        displayMaterial.setKeywords(config.SHADING ? ['SHADING'] : [])
      }
    ),
  ]

  window.addEventListener('mousedown', handleMouseDown)
  document.body.addEventListener('mousemove', handleFirstMouseMove)
  window.addEventListener('mousemove', handleMouseMove)
  document.body.addEventListener('touchstart', handleFirstTouchStart)
  window.addEventListener('touchstart', handleTouchStart)
  window.addEventListener('touchmove', handleTouchMove)
  window.addEventListener('touchend', handleTouchEnd)
  update()

  disposeFluidCursor = () => {
    destroyed = true
    if (animationFrameId !== null) {
      window.cancelAnimationFrame(animationFrameId)
      animationFrameId = null
    }
    window.removeEventListener('mousedown', handleMouseDown)
    document.body.removeEventListener('mousemove', handleFirstMouseMove)
    window.removeEventListener('mousemove', handleMouseMove)
    document.body.removeEventListener('touchstart', handleFirstTouchStart)
    window.removeEventListener('touchstart', handleTouchStart)
    window.removeEventListener('touchmove', handleTouchMove)
    window.removeEventListener('touchend', handleTouchEnd)
    stopWatchers.forEach(stop => stop())
    destroyDoubleFramebuffer(dye)
    destroyDoubleFramebuffer(velocity)
    destroyFramebuffer(curlTarget)
    destroyFramebuffer(divergenceTarget)
    destroyDoubleFramebuffer(pressure)
    gl.deleteBuffer(quadVertexBuffer)
    gl.deleteBuffer(quadIndexBuffer)
    copyProgram.dispose()
    clearProgram.dispose()
    splatProgram.dispose()
    advectionProgram.dispose()
    divergenceProgram.dispose()
    curlProgram.dispose()
    vorticityProgram.dispose()
    pressureProgram.dispose()
    gradientProgram.dispose()
    displayMaterial.dispose()
    gl.deleteShader(vertexShader)
    dye = null
    velocity = null
    curlTarget = null
    divergenceTarget = null
    pressure = null
  }
})

onUnmounted(() => {
  disposeFluidCursor?.()
  disposeFluidCursor = null
})
</script>

<style scoped>
.fluid-cursor {
  position: fixed;
  inset: 0;
  z-index: 50;
  width: 100vw;
  height: 100vh;
  pointer-events: none;
}

.fluid-cursor__canvas {
  display: block;
  width: 100vw;
  height: 100vh;
}
</style>
