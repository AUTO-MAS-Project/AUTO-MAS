/** 48³ 世界空间体素以 8×6 切片存储；atlas 只改变布局，求解和采样始终使用 xyz。 */
export const GRID_SIZE = 48
export const ATLAS_COLUMNS = 8
export const ATLAS_ROWS = 6
export const FIELD_HALF_SIZE = 3

export const atlasSampling = `
  const float gridSize = ${GRID_SIZE.toFixed(1)};
  const vec2 atlasTiles = vec2(${ATLAS_COLUMNS.toFixed(1)},${ATLAS_ROWS.toFixed(1)});
  vec2 sliceUv(vec2 cell, float z) {
    return (vec2(mod(z,atlasTiles.x),floor(z/atlasTiles.x))*gridSize+cell+.5)/(atlasTiles*gridSize);
  }
  vec3 voxelPosition(vec2 uv) {
    vec2 pixel = floor(uv*atlasTiles*gridSize);
    vec2 tile = floor(pixel/gridSize);
    return (vec3(mod(pixel,gridSize),tile.x+tile.y*atlasTiles.x)+.5)/gridSize;
  }
  vec4 sampleField(sampler2D field, vec3 point) {
    vec3 p = clamp(point*gridSize-.5,vec3(0.0),vec3(gridSize-1.0));
    float z = floor(p.z);
    return mix(texture2D(field,sliceUv(p.xy,z)),
               texture2D(field,sliceUv(p.xy,min(z+1.0,gridSize-1.0))),fract(p.z));
  }
`
const header = `
  varying vec2 vUv;
  uniform sampler2D velocity;
  uniform sampler2D source;
  uniform sampler2D pressure;
  uniform sampler2D divergence;
  uniform float dt;
  ${atlasSampling}
`
export const fluidVertex = `
  varying vec2 vUv;
  void main() { vUv=uv; gl_Position=vec4(position.xy,0.0,1.0); }
`
export const advect3d = `${header}
  uniform float dissipation;
  void main() {
    vec3 p=voxelPosition(vUv);
    gl_FragColor=sampleField(source,p-dt*sampleField(velocity,p).xyz)/(1.0+dissipation*dt);
  }
`
export const inject3d = `${header}
  uniform vec4 points[24]; uniform vec3 momenta[24]; uniform vec3 colors[24];
  uniform int sourceCount; uniform float dyeMode;
  void main() {
    vec3 p=voxelPosition(vUv); vec3 value=texture2D(source,vUv).xyz;
    for(int i=0;i<24;i++) {
      if(i>=sourceCount) break;
      vec3 delta=p-points[i].xyz;
      float weight=exp(-dot(delta,delta)/.0012)*points[i].w;
      value+=mix(momenta[i]*5.0,colors[i]*7.0,dyeMode)*weight;
    }
    gl_FragColor=vec4(clamp(value,vec3(-.6*(1.0-dyeMode)),vec3(.6+1.4*dyeMode)),1.0);
  }
`
export const divergence3d = `${header}
  void main() {
    vec3 p=voxelPosition(vUv); float h=1.0/gridSize;
    float l=sampleField(velocity,p-vec3(h,0,0)).x;
    float r=sampleField(velocity,p+vec3(h,0,0)).x;
    float b=sampleField(velocity,p-vec3(0,h,0)).y;
    float t=sampleField(velocity,p+vec3(0,h,0)).y;
    float d=sampleField(velocity,p-vec3(0,0,h)).z;
    float u=sampleField(velocity,p+vec3(0,0,h)).z;
    vec3 c=sampleField(velocity,p).xyz;
    if(p.x<h) l=-c.x; if(p.x>1.0-h) r=-c.x;
    if(p.y<h) b=-c.y; if(p.y>1.0-h) t=-c.y;
    if(p.z<h) d=-c.z; if(p.z>1.0-h) u=-c.z;
    gl_FragColor=vec4((r-l+t-b+u-d)*(.5/h),0,0,1);
  }
`
export const pressure3d = `${header}
  void main() {
    vec3 p=voxelPosition(vUv); float h=1.0/gridSize;
    float sum=sampleField(pressure,p-vec3(h,0,0)).x+sampleField(pressure,p+vec3(h,0,0)).x
      +sampleField(pressure,p-vec3(0,h,0)).x+sampleField(pressure,p+vec3(0,h,0)).x
      +sampleField(pressure,p-vec3(0,0,h)).x+sampleField(pressure,p+vec3(0,0,h)).x;
    gl_FragColor=vec4((sum-h*h*texture2D(divergence,vUv).x)/6.0,0,0,1);
  }
`
export const project3d = `${header}
  void main() {
    vec3 p=voxelPosition(vUv); float h=1.0/gridSize;
    vec3 gradient=vec3(
      sampleField(pressure,p+vec3(h,0,0)).x-sampleField(pressure,p-vec3(h,0,0)).x,
      sampleField(pressure,p+vec3(0,h,0)).x-sampleField(pressure,p-vec3(0,h,0)).x,
      sampleField(pressure,p+vec3(0,0,h)).x-sampleField(pressure,p-vec3(0,0,h)).x)*(.5/h);
    vec3 value=clamp(texture2D(velocity,vUv).xyz-gradient,vec3(-.6),vec3(.6));
    if(p.x<h||p.x>1.0-h) value.x=0.0;
    if(p.y<h||p.y>1.0-h) value.y=0.0;
    if(p.z<h||p.z>1.0-h) value.z=0.0;
    gl_FragColor=vec4(value,1.0);
  }
`
