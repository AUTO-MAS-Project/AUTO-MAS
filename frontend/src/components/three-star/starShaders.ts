export const starVertex = `
  varying vec3 vNormal; varying vec3 vPosition;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    vPosition = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`
export const starFragment = `
  varying vec3 vNormal; varying vec3 vPosition;
  uniform vec3 color; uniform float time; uniform float dark; uniform float flash;
  float grain(vec3 p) {
    return sin(p.x*17.0 + sin(p.y*13.0 + time*.32)) *
      sin(p.y*21.0 + sin(p.z*19.0-time*.28)) * sin(p.z*23.0+p.x*11.0);
  }
  void main() {
    vec3 p = normalize(vPosition);
    float flow = grain(p*1.2) * .5 + grain(p*2.7)*.2;
    float limb = pow(max(0.0,vNormal.z), .45);
    vec3 base = mix(color*.38, mix(color,vec3(1.0),.28), .35+limb*.65);
    base *= .83 + .20*flow;
    base += color * flash * .22;
    gl_FragColor = vec4(base * mix(.7,1.0,dark), 1.0);
  }
`
export const coronaFragment = `
  varying vec2 vUv;
  uniform vec3 color; uniform float time; uniform float dark; uniform float flash;
  void main() {
    vec2 p = vUv*2.0-1.0;
    float r=length(p); float angle=atan(p.y,p.x);
    float tongue = sin(angle*9.0 + time*.45 + sin(angle*5.0-time*.3));
    float rim = .46 + .025*tongue;
    float halo = exp(-max(0.0,r-rim)*12.0) * smoothstep(.36,.48,r);
    float flame = pow(max(0.0,tongue),5.0)*exp(-abs(r-.54)*22.0)*.25;
    float alpha = min(.38,(halo*.28+flame)*mix(.65,1.0,dark) + flash*.07*halo);
    gl_FragColor=vec4(color,alpha*(1.0-smoothstep(.82,1.0,r)));
  }
`
export const quadVertex = `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }
`
export const fluidCompositeFragment = `
  varying vec2 vUv;
  uniform sampler2D dye; uniform float dark;
  void main() {
    vec3 value = max(vec3(0.0),texture2D(dye,vUv).rgb);
    float density = max(value.r,max(value.g,value.b));
    vec3 color = value / max(.001,density);
    color = mix(color*.52,color,dark);
    // 亮度/覆盖率均有界，不采用无限加法叠白。
    gl_FragColor = vec4(color,min(.30,density*.65));
  }
`
