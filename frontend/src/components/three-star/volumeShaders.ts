import { atlasSampling, FIELD_HALF_SIZE, fluidVertex } from './fluid3dShaders'
import { stellarNoise } from './starShaders'

export const screenVertex = fluidVertex
const viewRay = `
  varying vec2 vUv;
  uniform mat4 inverseProjection; uniform mat4 viewToWorld;
  vec3 rayDirection() {
    vec4 view = inverseProjection*vec4(vUv*2.0-1.0,1.0,1.0);
    return normalize(mat3(viewToWorld)*(view.xyz/view.w));
  }
`
export const skyFragment = `${viewRay}
  uniform sampler2D sky; uniform float dark;
  void main() {
    vec3 ray=rayDirection();
    vec2 uv=vec2(fract(atan(ray.z,ray.x)/6.2831853+.62),asin(clamp(ray.y,-1.0,1.0))/3.1415927+.5);
    vec3 stars=texture2D(sky,uv).rgb;
    gl_FragColor=vec4(stars*mix(.72,.9,dark)+vec3(.002,.004,.009),1.0);
    #include <colorspace_fragment>
  }
`

/** 世界空间光线步进；不透明球面截断整条射线，后方气体不会透过星体。 */
export const volumeFragment = `${viewRay}
  uniform sampler2D dye; uniform vec3 eye;
  uniform vec3 centers[3]; uniform vec3 colors[3];
  uniform float flashes[3]; uniform float time; uniform float dark;
  ${atlasSampling}
  ${stellarNoise}
  const float halfSize=${FIELD_HALF_SIZE.toFixed(1)};
  const float starRadius=.17;
  const float coronaRadius=.4;
  vec2 sphereRange(vec3 ray,vec3 center,float radius) {
    vec3 offset=eye-center; float b=dot(offset,ray);
    float discriminant=b*b-dot(offset,offset)+radius*radius;
    if(discriminant<0.0) return vec2(1e6,-1e6);
    float root=sqrt(discriminant);
    return vec2(-b-root,-b+root);
  }
  void main() {
    vec3 ray=rayDirection();
    // 光线与立方体交集。近零方向保留符号，避免轴平行时的 NaN。
    vec3 safeRay=mix(vec3(-1.0),vec3(1.0),step(vec3(0.0),ray))*max(abs(ray),vec3(1e-6));
    vec3 lo=(-vec3(halfSize)-eye)/safeRay, hi=(vec3(halfSize)-eye)/safeRay;
    vec3 nearPlane=min(lo,hi),farPlane=max(lo,hi);
    vec2 ranges[4];
    ranges[0]=vec2(max(0.0,max(nearPlane.x,max(nearPlane.y,nearPlane.z))),min(farPlane.x,min(farPlane.y,farPlane.z)));
    float first=1e6,last=0.0,opaque=1e6;
    for(int i=0;i<3;i++) {
      ranges[i+1]=sphereRange(ray,centers[i],coronaRadius);
      ranges[i+1].x=max(0.0,ranges[i+1].x);
      vec2 solid=sphereRange(ray,centers[i],starRadius);
      if(solid.y>0.0) opaque=min(opaque,max(0.0,solid.x));
    }
    for(int i=0;i<4;i++) if(ranges[i].y>ranges[i].x) {
      first=min(first,ranges[i].x);last=max(last,ranges[i].y);
    }
    last=min(last,opaque);
    vec3 result=vec3(0.0);float alpha=0.0,t=first;
    // 粗步走体素，日冕局部细步；空白区直接跳到下一有效区间。
    for(int stepIndex=0;stepIndex<288;stepIndex++) {
      if(t>=last||alpha>.92) break;
      bool active=false,nearCorona=false;float boundary=last,nextEntry=last;
      for(int i=0;i<4;i++) {
        if(ranges[i].y<=ranges[i].x) continue;
        if(t>=ranges[i].x&&t<ranges[i].y) {
          active=true;boundary=min(boundary,ranges[i].y);
          if(i>0) nearCorona=true;
        } else if(ranges[i].x>t) nextEntry=min(nextEntry,ranges[i].x);
      }
      if(!active) { t=nextEntry;continue; }
      float ds=min(nearCorona?.018:.09,min(boundary,nextEntry)-t);
      // 边界舍入导致零步时只推进显示采样，不触碰物理积分器。
      if(ds<1e-5) {t+=1e-5;continue;}
      vec3 p=eye+ray*(t+ds*.5),emission=vec3(0.0);float density=0.0;
      if(all(lessThanEqual(abs(p),vec3(halfSize)))) {
        vec3 gas=max(vec3(0.0),sampleField(dye,p/(2.0*halfSize)+.5).rgb);
        float d=max(gas.r,max(gas.g,gas.b));
        density=d*1.8;emission=gas*1.8;
      }
      for(int i=0;i<3;i++) {
        vec3 q=p-centers[i];float r=length(q);
        if(r>starRadius&&r<coronaRadius) {
          vec3 flow=q*28.0+vec3(time*.13,-time*.09,time*.07)+float(i)*7.0;
          float n=noise3(flow+noise3(flow*.4)*1.5);
          float ribbon=pow(max(0.0,1.0-abs(n-.53)*6.0),3.0);
          float shell=exp(-(r-starRadius)*24.0);
          float plume=smoothstep(.55,.78,n)*exp(-(r-starRadius)*12.0);
          float d=(shell*(.5+ribbon*3.0)+plume*1.6)*(1.0+flashes[i]*.4);
          density+=d;emission+=colors[i]*d;
        }
      }
      float a=1.0-exp(-density*ds);
      result+=(1.0-alpha)*a*emission/max(density,.0001);
      alpha+=(1.0-alpha)*a;t+=ds;
    }
    // 有界覆盖与亮度，采用预乘透明度合成，避免反复加法叠白。
    float opacity=min(.78,alpha)*mix(.92,1.0,dark);
    gl_FragColor=vec4(clamp(result/max(alpha,.0001),0.0,1.0)*opacity,opacity);
  }
`
export const volumeOutputFragment = `
  varying vec2 vUv; uniform sampler2D volume;
  void main() {
    vec4 value=texture2D(volume,vUv);
    gl_FragColor=vec4(value.rgb/max(value.a,.0001),value.a);
    #include <colorspace_fragment>
  }
`
