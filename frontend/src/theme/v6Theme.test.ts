import { describe, expect, it } from 'vitest'

import {
  V6_THEME_PALETTES,
  V6_UI_SCALE_DEFAULT,
  V6_UI_SCALE_MAX,
  V6_UI_SCALE_MIN,
  buildV6AntThemeTokens,
  buildV6ThemeCssVariables,
  detectLowPerfMode,
  normalizeUiScale,
} from './v6Theme'

describe('v6 theme contract', () => {
  it('maps light and dark surfaces without losing semantic status colors', () => {
    const light = buildV6AntThemeTokens(false, '#1677ff', 1)
    const dark = buildV6AntThemeTokens(true, '#0a84ff', 1)

    expect(light.colorBgLayout).toBe(V6_THEME_PALETTES.light.layout)
    expect(dark.colorBgLayout).toBe(V6_THEME_PALETTES.dark.layout)
    expect(light.colorText).not.toBe(dark.colorText)
    expect(dark.colorSuccess).toBe('#30d158')
    expect(dark.colorError).toBe('#ff453a')
  })

  it('normalizes UI scale to stable five-percent steps and safe bounds', () => {
    expect(normalizeUiScale('1.23')).toBe(1.25)
    expect(normalizeUiScale(0.2)).toBe(0.8)
    expect(normalizeUiScale(2)).toBe(1.4)
    expect(normalizeUiScale('invalid')).toBe(1)
    expect(normalizeUiScale(null)).toBe(1)
  })

  it('scales Ant Design controls and publishes the same CSS scale', () => {
    const tokens = buildV6AntThemeTokens(false, '#1677ff', 1.25)
    const cssVariables = buildV6ThemeCssVariables(false, 1.25)

    expect(tokens.fontSize).toBe(18)
    expect(tokens.controlHeight).toBe(40)
    expect(cssVariables['--v6-ui-scale']).toBe('1.25')
  })
})

describe('normalizeUiScale bounds and rounding', () => {
  it('keeps the exact boundary values 0.8 and 1.4 without clamping', () => {
    expect(normalizeUiScale(0.8)).toBe(V6_UI_SCALE_MIN)
    expect(normalizeUiScale(1.4)).toBe(V6_UI_SCALE_MAX)
    expect(normalizeUiScale('0.8')).toBe(0.8)
    expect(normalizeUiScale('1.4')).toBe(1.4)
  })

  it('clamps out-of-range values into the safe window', () => {
    expect(normalizeUiScale(0.5)).toBe(0.8)
    expect(normalizeUiScale(1.5)).toBe(1.4)
    expect(normalizeUiScale(-1)).toBe(0.8)
    expect(normalizeUiScale(10)).toBe(1.4)
  })

  it('rounds to the nearest 1/20 step and falls back for invalid input', () => {
    expect(normalizeUiScale(1.1)).toBe(1.1)
    expect(normalizeUiScale(1.12)).toBe(1.1)
    expect(normalizeUiScale(1.13)).toBe(1.15)
    expect(normalizeUiScale(undefined)).toBe(V6_UI_SCALE_DEFAULT)
    expect(normalizeUiScale('')).toBe(V6_UI_SCALE_DEFAULT)
    expect(normalizeUiScale('not-a-number')).toBe(V6_UI_SCALE_DEFAULT)
    expect(normalizeUiScale(Number.NaN)).toBe(V6_UI_SCALE_DEFAULT)
  })
})

describe('buildV6ThemeCssVariables palette mapping', () => {
  it('publishes light palette values and the normalized scale for light mode', () => {
    const vars = buildV6ThemeCssVariables(false, 1.2)

    expect(vars['--v6-ui-scale']).toBe('1.2')
    expect(vars['--v6-color-window']).toBe(V6_THEME_PALETTES.light.layout)
    expect(vars['--v6-color-surface']).toBe(V6_THEME_PALETTES.light.container)
    expect(vars['--v6-color-text']).toBe(V6_THEME_PALETTES.light.text)
    expect(vars['--v6-color-info']).toBe(V6_THEME_PALETTES.light.info)
  })

  it('publishes dark palette values for dark mode', () => {
    const vars = buildV6ThemeCssVariables(true, 1)

    expect(vars['--v6-color-window']).toBe(V6_THEME_PALETTES.dark.layout)
    expect(vars['--v6-color-surface']).toBe(V6_THEME_PALETTES.dark.container)
    expect(vars['--v6-color-text']).toBe(V6_THEME_PALETTES.dark.text)
    expect(vars['--v6-color-border']).toBe(V6_THEME_PALETTES.dark.border)
  })

  it('emits the eight vibrancy surfaces and keeps them distinct between modes', () => {
    const light = buildV6ThemeCssVariables(false, 1)
    const dark = buildV6ThemeCssVariables(true, 1)
    const vibrancyKeys = [
      '--v6-vibrancy-sidebar',
      '--v6-vibrancy-titlebar',
      '--v6-vibrancy-toolbar',
      '--v6-vibrancy-content',
      '--v6-vibrancy-popover',
      '--v6-vibrancy-hover',
      '--v6-vibrancy-selected',
      '--v6-vibrancy-active',
    ]

    for (const key of vibrancyKeys) {
      expect(light[key]).toBeTruthy()
      expect(dark[key]).toBeTruthy()
      expect(light[key]).not.toBe(dark[key])
    }
  })
})

describe('buildV6AntThemeTokens scaling and passthrough', () => {
  it('passes the primary color through and scales fontSize/controlHeight from base 14/32', () => {
    const tokens = buildV6AntThemeTokens(false, '#ff0000', 1)

    expect(tokens.colorPrimary).toBe('#ff0000')
    expect(tokens.fontSize).toBe(14)
    expect(tokens.controlHeight).toBe(32)
    expect(tokens.borderRadius).toBe(6)
  })

  it('scales controls at the upper and lower bounds', () => {
    const max = buildV6AntThemeTokens(true, '#0a84ff', 1.4)
    const min = buildV6AntThemeTokens(false, '#007aff', 0.8)

    expect(max.fontSize).toBe(Math.round(14 * 1.4))
    expect(max.controlHeight).toBe(Math.round(32 * 1.4))
    expect(min.fontSize).toBe(Math.round(14 * 0.8))
    expect(min.controlHeight).toBe(Math.round(32 * 0.8))
  })

  it('keeps boxShadowSecondary dependent on the mode', () => {
    const light = buildV6AntThemeTokens(false, '#007aff', 1)
    const dark = buildV6AntThemeTokens(true, '#0a84ff', 1)

    expect(light.boxShadowSecondary).not.toBe(dark.boxShadowSecondary)
    expect(dark.boxShadowSecondary).toContain('36%')
  })
})

describe('V6_THEME_PALETTES structure', () => {
  const requiredFields = [
    'layout',
    'container',
    'elevated',
    'titlebar',
    'sidebar',
    'text',
    'textSecondary',
    'textTertiary',
    'border',
    'borderSecondary',
    'success',
    'warning',
    'error',
    'info',
  ] as const

  for (const mode of ['light', 'dark'] as const) {
    it(`exposes every semantic field for the ${mode} palette`, () => {
      const palette = V6_THEME_PALETTES[mode]
      for (const field of requiredFields) {
        expect(palette[field]).toBeTruthy()
      }
    })
  }

  it('keeps status colors as plain hex for both modes', () => {
    for (const mode of ['light', 'dark'] as const) {
      const palette = V6_THEME_PALETTES[mode]
      for (const field of ['success', 'warning', 'error', 'info'] as const) {
        expect(palette[field]).toMatch(/^#[0-9a-f]{6}$/i)
      }
    }
  })
})

describe('detectLowPerfMode hardware gating', () => {
  it('returns low when cores or memory are below the threshold', () => {
    expect(detectLowPerfMode({ hardwareConcurrency: 2 })).toBe('low')
    expect(detectLowPerfMode({ deviceMemory: 2 })).toBe('low')
    expect(detectLowPerfMode({ prefersReducedMotion: true })).toBe('low')
  })

  it('returns normal for capable hardware and ignores missing signals', () => {
    expect(detectLowPerfMode({ hardwareConcurrency: 8, deviceMemory: 8 })).toBe('normal')
    expect(detectLowPerfMode({})).toBe('normal')
    expect(detectLowPerfMode({ hardwareConcurrency: 0, deviceMemory: 0 })).toBe('normal')
  })
})
