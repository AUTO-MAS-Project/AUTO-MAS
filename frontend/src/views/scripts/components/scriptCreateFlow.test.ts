import { describe, expect, it } from 'vitest'
import {
  buildCreateRequest,
  buildCreateSteps,
  filterScriptTypeOptions,
  getScriptEditSegment,
  SCRIPT_TYPE_OPTIONS,
  splitScriptTypeOptions,
} from './scriptCreateFlow'

describe('scriptCreateFlow', () => {
  it('builds the copy path', () => {
    expect(buildCreateSteps({ mode: 'copy', type: 'MAA' }).map(step => step.key)).toEqual([
      'mode',
      'script',
    ])
  })

  it('adds the config step only for General scripts', () => {
    expect(buildCreateSteps({ mode: 'new', type: 'General' }).map(step => step.key)).toEqual([
      'mode',
      'type',
      'config',
    ])
    expect(buildCreateSteps({ mode: 'new', type: 'M9A' }).map(step => step.key)).toEqual([
      'mode',
      'type',
    ])
  })

  it('filters script types by aliases and group', () => {
    expect(filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, '1999').map(item => item.value)).toEqual([
      'M9A',
    ])
  })

  it('separates specialized adapters from the General option', () => {
    const sections = splitScriptTypeOptions(SCRIPT_TYPE_OPTIONS)
    expect(sections.specialized.map(item => item.value)).not.toContain('General')
    expect(sections.general.map(item => item.value)).toEqual(['General'])
  })

  it('maps every script type to its edit route segment', () => {
    expect(getScriptEditSegment('MAA')).toBe('maa')
    expect(getScriptEditSegment('MaaEnd')).toBe('maaend')
    expect(getScriptEditSegment('Okww')).toBe('okww')
    expect(getScriptEditSegment('HSR')).toBe('hsr')
    expect(getScriptEditSegment('General')).toBe('general')
  })

  it('builds submit requests only when required selections exist', () => {
    expect(
      buildCreateRequest({
        mode: 'new',
        type: 'SRC',
        configMode: 'template',
        scriptId: null,
        template: null,
      })
    ).toEqual({ kind: 'new', type: 'SRC' })

    expect(
      buildCreateRequest({
        mode: 'new',
        type: 'General',
        configMode: 'custom',
        scriptId: null,
        template: null,
      })
    ).toEqual({ kind: 'general-custom' })

    expect(
      buildCreateRequest({
        mode: 'copy',
        type: 'MAA',
        configMode: 'template',
        scriptId: null,
        template: null,
      })
    ).toBeNull()
  })
})
