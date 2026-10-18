const stellarNoise = `
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
    vec3 core = mix(vec3(.003,.008,.02),color*.055,.3+facing*.7);
    vec3 electric = mix(color,vec3(.82,.95,1.0),.18);
    vec3 surface = core + electric*threads*(.35+facing*.4) + color*fresnel*.8;
    surface += mix(color,vec3(1.0),.45)*pow(threads,4.0)*.22;
    surface += color*flash*.12;
    gl_FragColor = vec4(clamp(surface*mix(.94,1.0,dark),0.0,1.0),1.0);
    #include <colorspace_fragment>
  }
`
export const coronaFragment = `
  varying vec2 vUv;
  uniform vec3 color; uniform float time; uniform float dark; uniform float flash;
  ${stellarNoise}
  void main() {
    vec2 p = vUv*2.0-1.0;
    float r=length(p); float angle=atan(p.y,p.x);
    float turbulence = noise3(vec3(p*13.0,time*.15));
    float ribbons = 1.0-smoothstep(.0,max(.012,fwidth(turbulence)*.65),abs(turbulence-.52));
    float tongue = .55+.45*sin(angle*7.0-time*.4+sin(angle*11.0+time*.2));
    float rim = .46 + .006*sin(angle*19.0+time*.3);
    float thinRim = exp(-abs(r-rim)*85.0);
    float halo = exp(-max(0.0,r-rim)*8.0)*smoothstep(.4,.47,r);
    float streams = ribbons*exp(-abs(r-.53)*13.0)*tongue;
    vec2 scatter = p*13.0+vec2(sin(time*.1),cos(time*.08))*.3;
    vec2 cell = floor(scatter);
    vec2 offset = vec2(hash31(vec3(cell,2)),hash31(vec3(cell,7)))*.7+.15;
    vec2 dustDelta = fract(scatter)-offset;
    float dust = exp(-dot(dustDelta,dustDelta)*110.0)*step(.97,hash31(vec3(cell,11)));
    dust *= smoothstep(.54,.68,r);
    float alpha = min(.68,(halo*.17+streams*.65+thinRim*.48+dust*.5+flash*halo*.12)*mix(.92,1.0,dark));
    vec3 corona = mix(color,vec3(.85,.97,1.0),min(.65,thinRim*.45+dust*.3));
    gl_FragColor=vec4(corona,alpha*(1.0-smoothstep(.8,1.0,r)));
    #include <colorspace_fragment>
  }
`
export const quadVertex = `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }
`
export const fluidCompositeFragment = `
  varying vec2 vUv;
  uniform sampler2D dye; uniform float dark;
  float hash21(vec2 p) {
    vec3 q = fract(vec3(p.xyx)*.1031);
    q += dot(q,q.yzx+33.33);
    return fract((q.x+q.y)*q.z);
  }
  void main() {
    // 深空底景局限在装饰区域，边缘透明；星尘是静态艺术背景。
    vec2 p = vUv-.5;
    float mask = 1.0-smoothstep(.22,.6,length(p*vec2(1.0,1.25)));
    float cloud = sin(vUv.x*8.0+sin(vUv.y*7.0))*sin(vUv.y*9.0-vUv.x*3.0)*.5+.5;
    vec3 space = mix(vec3(.006,.012,.03),vec3(.025,.045,.085),cloud);
    space += vec3(.028,.009,.04)*exp(-length(p-vec2(.18,.06))*8.0);
    vec2 grid = vUv*vec2(112.0,48.0);
    vec2 cell = floor(grid);
    vec2 offset = vec2(hash21(cell),hash21(cell+17.0))*.7+.15;
    float speck = (1.0-smoothstep(.015,.11,length(fract(grid)-offset))) * step(.955,hash21(cell+51.0));
    space += vec3(.32,.42,.58)*speck;
    vec3 value = max(vec3(0.0),texture2D(dye,vUv).rgb);
    float density = max(value.r,max(value.g,value.b));
    vec3 color = value / max(.001,density);
    float fluidAlpha = min(.6,(1.0-exp(-density*1.5))*.7)*mask;
    float spaceAlpha = mask*mix(.94,.55,dark);
    float alpha = fluidAlpha+spaceAlpha*(1.0-fluidAlpha);
    vec3 result = (color*fluidAlpha+space*spaceAlpha*(1.0-fluidAlpha))/max(.001,alpha);
    gl_FragColor = vec4(result,alpha);
    #include <colorspace_fragment>
  }
`
