export const stellarNoise = `
  float hash31(vec3 p) {
    p = fract(p * .1031);
    p += dot(p, p.yzx + 33.33);
    return fract((p.x + p.y) * p.z);
  }
  float noise3(vec3 p) {
    vec3 i = floor(p); vec3 f = fract(p);
    f = f*f*(3.0-2.0*f);
    return mix(
      mix(mix(hash31(i), hash31(i+vec3(1,0,0)), f.x),
          mix(hash31(i+vec3(0,1,0)), hash31(i+vec3(1,1,0)), f.x), f.y),
      mix(mix(hash31(i+vec3(0,0,1)), hash31(i+vec3(1,0,1)), f.x),
          mix(hash31(i+vec3(0,1,1)), hash31(i+vec3(1,1,1)), f.x), f.y), f.z);
  }
`

export const starVertex = `
  varying vec3 vNormal; varying vec3 vPosition; varying vec3 vViewPosition;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    vPosition = position;
    vec4 view = modelViewMatrix * vec4(position, 1.0);
    vViewPosition = view.xyz;
    gl_Position = projectionMatrix * view;
  }
`
export const starFragment = `
  varying vec3 vNormal; varying vec3 vPosition; varying vec3 vViewPosition;
  uniform vec3 color; uniform float time; uniform float dark; uniform float flash;
  ${stellarNoise}
  void main() {
    vec3 p = normalize(vPosition);
    vec3 drift = vec3(time*.11,-time*.07,time*.05);
    float warp = noise3(p*3.4-drift*.7);
    vec3 flow = p*5.5 + drift + vec3(warp,-warp,warp*.6)*1.6;
    float field = noise3(flow) + noise3(flow*2.1+4.7)*.22;
    float branch = noise3(flow*1.7-2.3);
    // 噪声等值线构成球面的能量丝，屏幕导数控制细线宽度，避免硬阈值闪烁。
    float seam = 1.0-smoothstep(.0,max(.008,fwidth(field)*.65),abs(field-.58));
    float fine = 1.0-smoothstep(.0,max(.006,fwidth(branch)*.5),abs(branch-.49));
    float threads = min(1.0,seam + fine*smoothstep(.4,.7,field)*.55);
    float facing = max(0.0,dot(normalize(vNormal),normalize(-vViewPosition)));
    float fresnel = pow(1.0-facing,2.6);
    // 宽尺度表面与明暗层次提供体积感，细丝只作为表面细节。
    float granules = noise3(flow*2.4+3.1);
    float light = .18+.5*pow(facing,.7);
    vec3 core = color*(.14+granules*.26)*light;
    vec3 electric = mix(color,vec3(.82,.95,1.0),.18);
    vec3 surface = core + electric*threads*(.22+facing*.28) + color*fresnel*.65;
    surface += mix(color,vec3(1.0),.45)*pow(threads,4.0)*.22;
    surface += color*flash*.12;
    gl_FragColor = vec4(clamp(surface*mix(.94,1.0,dark),0.0,1.0),1.0);
    #include <colorspace_fragment>
  }
`
