/** 主页卫星样式：3D 星系，或原来的平面卫星（经典） */
export type HomeSatelliteStyle = 'galaxy' | 'classic'

export const DEFAULT_HOME_SATELLITE_STYLE: HomeSatelliteStyle = 'galaxy'

export const normalizeHomeSatelliteStyle = (value: unknown): HomeSatelliteStyle =>
  value === 'classic' ? 'classic' : DEFAULT_HOME_SATELLITE_STYLE
