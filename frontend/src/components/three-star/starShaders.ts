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
    vec3 flow = p*6.0 + vec3(time*.14, -time*.09, time*.06);
    float convection = noise3(flow + noise3(p*3.0-time*.09)*1.8);
    float granules = noise3(flow*3.5 + convection);
    float hot = smoothstep(.28,.82,convection*.65+granules*.35);
    float facing = max(0.0,dot(normalize(vNormal),normalize(-vViewPosition)));
    float limb = pow(facing,.38);
    vec3 surface = mix(color*.24,mix(color,vec3(1.0),.7),hot);
    surface *= (.28 + .72*limb)*mix(.94,1.0,dark);
    surface += color*pow(1.0-facing,3.0)*.32 + color*flash*.18;
    gl_FragColor = vec4(clamp(surface,0.0,1.0),1.0);
    #include <colorspace_fragment>
  }
`
export const coronaFragment = `
  varying vec2 vUv;
  uniform vec3 color; uniform float time; uniform float dark; uniform float flash;
  void main() {
    vec2 p = vUv*2.0-1.0;
    float r=length(p); float angle=atan(p.y,p.x);
    float tongue = sin(angle*7.0-time*.55+sin(angle*11.0+time*.24));
    float filaments = .5+.5*sin(angle*37.0 + sin(angle*13.0-time*.4)*2.0-r*28.0);
    float rim = .46 + .012*sin(angle*19.0+time*.38);
    float halo = exp(-max(0.0,r-rim)*8.0)*smoothstep(.39,.47,r);
    float threads = pow(max(0.0,tongue),4.0)*filaments*exp(-abs(r-.56)*13.0);
    float thinRim = exp(-abs(r-rim)*75.0);
    float alpha = min(.62,(halo*.2+threads*.42+thinRim*.3+flash*halo*.12)*mix(.92,1.0,dark));
    vec3 corona = mix(color,vec3(1.0),thinRim*.4);
    gl_FragColor=vec4(corona,alpha*(1.0-smoothstep(.78,1.0,r)));
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
