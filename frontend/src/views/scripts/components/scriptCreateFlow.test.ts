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
    expect(buildCreateSteps({ type: 'Simple' }).map(step => step.key)).toEqual(['type'])
    expect(buildCreateSteps({ type: 'M9A' }).map(step => step.key)).toEqual(['type'])
  })

  it('registers every supported script type', () => {
    expect(SCRIPT_TYPE_OPTIONS.map(option => option.value)).toEqual([
      'General',
      'Simple',
      'MAA',
      'SRC',
      'MaaEnd',
      'M9A',
      'Okww',
      'OkNte',
      'HSR',
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

  it('separates specialized adapters from the General group', () => {
    const sections = splitScriptTypeOptions(SCRIPT_TYPE_OPTIONS)
    expect(sections.specialized.map(item => item.value)).not.toContain('General')
    expect(sections.general.map(item => item.value)).toEqual(['General', 'Simple'])
  })

  it('maps every script type to its edit route segment', () => {
    expect(getScriptEditSegment('MAA')).toBe('maa')
    expect(getScriptEditSegment('MaaEnd')).toBe('maaend')
    expect(getScriptEditSegment('Okww')).toBe('okww')
    expect(getScriptEditSegment('OkNte')).toBe('oknte')
    expect(getScriptEditSegment('HSR')).toBe('hsr')
    expect(getScriptEditSegment('General')).toBe('general')
    expect(getScriptEditSegment('Simple')).toBe('simple')
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
        type: 'Simple',
        configMode: 'template',
        template: null,
      })
    ).toEqual({ kind: 'new', type: 'Simple' })

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
