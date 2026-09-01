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
  it('starts with script type and adds the config step only for General scripts', () => {
    expect(buildCreateSteps({ type: 'General' }).map(step => step.key)).toEqual(['type', 'config'])
    expect(buildCreateSteps({ type: 'M9A' }).map(step => step.key)).toEqual(['type'])
  })

  it('registers every supported script type', () => {
    expect(SCRIPT_TYPE_OPTIONS.map(option => option.value)).toEqual([
      'General',
      'MAA',
      'SRC',
      'MaaEnd',
      'M9A',
      'MaaFW',
      'Okww',
      'OkNte',
      'HSR',
      'BetterGI',
    ])
  })

  it('filters script types by aliases and group', () => {
    expect(filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, '1999').map(item => item.value)).toEqual([
      'M9A',
    ])
    expect(filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, '异环').map(item => item.value)).toEqual([
      'OkNte',
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
    expect(getScriptEditSegment('OkNte')).toBe('oknte')
    expect(getScriptEditSegment('HSR')).toBe('hsr')
    expect(getScriptEditSegment('BetterGI')).toBe('bettergi')
    expect(getScriptEditSegment('General')).toBe('general')
  })

  it('builds submit requests only when required selections exist', () => {
    expect(
      buildCreateRequest({
        type: 'SRC',
        configMode: 'template',
        template: null,
      })
    ).toEqual({ kind: 'new', type: 'SRC' })

    expect(
      buildCreateRequest({
        type: 'General',
        configMode: 'custom',
        template: null,
      })
    ).toEqual({ kind: 'general-custom' })

    expect(
      buildCreateRequest({
        type: 'General',
        configMode: 'template',
        template: null,
      })
    ).toBeNull()
  })
})
