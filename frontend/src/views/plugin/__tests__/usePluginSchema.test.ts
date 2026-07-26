import { describe, expect, it } from 'vitest'
import {
  isBooleanSchema,
  isStringSchema,
  isNumberSchema,
  isListSchema,
  isPasswordSchema,
  isUrlSchema,
  isEnumSchema,
  isEnumListSchema,
  isButtonSchema,
  hasEnableSchema,
  toFiniteNumber,
  getFieldLabel,
  getTypeLabel,
  getSchemaButtonAction,
  parseConfigText,
  setConfigObjectToText,
  isValidHttpUrl,
  validateSchemaFieldValue,
  collectSchemaFieldErrors,
} from '../composables/usePluginSchema'
import type { PluginSchemaField } from '../types'

function field(overrides: Partial<PluginSchemaField> = {}): PluginSchemaField {
  return { type: 'string', ...overrides }
}

describe('usePluginSchema', () => {
  describe('type guards', () => {
    it('isBooleanSchema detects boolean types', () => {
      expect(isBooleanSchema(field({ type: 'boolean' }))).toBe(true)
      expect(isBooleanSchema(field({ type: 'bool' }))).toBe(true)
      expect(isBooleanSchema(field({ type: 'string' }))).toBe(false)
    })

    it('isStringSchema detects string types', () => {
      expect(isStringSchema(field({ type: 'string' }))).toBe(true)
      expect(isStringSchema(field({ type: 'str' }))).toBe(true)
      expect(isStringSchema(field({ type: 'number' }))).toBe(false)
    })

    it('isNumberSchema detects number types', () => {
      expect(isNumberSchema(field({ type: 'number' }))).toBe(true)
      expect(isNumberSchema(field({ type: 'integer' }))).toBe(true)
      expect(isNumberSchema(field({ type: 'int' }))).toBe(true)
      expect(isNumberSchema(field({ type: 'float' }))).toBe(true)
      expect(isNumberSchema(field({ type: 'string' }))).toBe(false)
    })

    it('isListSchema detects list types', () => {
      expect(isListSchema(field({ type: 'list' }))).toBe(true)
      expect(isListSchema(field({ type: 'list[str]' }))).toBe(true)
      expect(isListSchema(field({ type: 'string' }))).toBe(false)
    })

    it('isPasswordSchema detects password format', () => {
      expect(isPasswordSchema(field({ type: 'string', format: 'password' }))).toBe(true)
      expect(isPasswordSchema(field({ type: 'string' }))).toBe(false)
    })

    it('isUrlSchema detects url format', () => {
      expect(isUrlSchema(field({ type: 'string', format: 'url' }))).toBe(true)
      expect(isUrlSchema(field({ type: 'string' }))).toBe(false)
    })

    it('isEnumSchema detects enum without list', () => {
      expect(isEnumSchema(field({ type: 'string', enum: ['a', 'b'] }))).toBe(true)
      expect(isEnumSchema(field({ type: 'string', enum: [] }))).toBe(false)
    })

    it('isEnumListSchema detects enum with list', () => {
      expect(isEnumListSchema(field({ type: 'list', enum: ['a', 'b'] }))).toBe(true)
      expect(isEnumListSchema(field({ type: 'string', enum: ['a', 'b'] }))).toBe(false)
    })

    it('isButtonSchema detects button/action types', () => {
      expect(isButtonSchema(field({ type: 'button' }))).toBe(true)
      expect(isButtonSchema(field({ type: 'action' }))).toBe(true)
      expect(isButtonSchema(field({ type: 'string' }))).toBe(false)
    })
  })

  describe('hasEnableSchema', () => {
    it('returns true when schema has boolean enable field', () => {
      const schemaMap = {
        plugin1: { enable: field({ type: 'boolean' }) },
      }
      expect(hasEnableSchema('plugin1', schemaMap)).toBe(true)
    })

    it('returns false when schema lacks enable field', () => {
      const schemaMap = {
        plugin1: { name: field({ type: 'string' }) },
      }
      expect(hasEnableSchema('plugin1', schemaMap)).toBe(false)
    })

    it('returns false when pluginName is undefined', () => {
      expect(hasEnableSchema(undefined, {})).toBe(false)
    })
  })

  describe('toFiniteNumber', () => {
    it('returns number for valid number', () => {
      expect(toFiniteNumber(42)).toBe(42)
    })

    it('returns number for valid string', () => {
      expect(toFiniteNumber('42')).toBe(42)
    })

    it('returns undefined for NaN', () => {
      expect(toFiniteNumber('abc')).toBeUndefined()
    })

    it('returns undefined for Infinity', () => {
      expect(toFiniteNumber(Infinity)).toBeUndefined()
    })
  })

  describe('getFieldLabel', () => {
    it('prefers title', () => {
      expect(getFieldLabel('myField', field({ title: 'My Title', description: 'Desc' }))).toBe(
        'My Title'
      )
    })

    it('falls back to description', () => {
      expect(getFieldLabel('myField', field({ description: 'Desc' }))).toBe('Desc')
    })

    it('falls back to field name', () => {
      expect(getFieldLabel('myField', field({}))).toBe('myField')
    })
  })

  describe('getTypeLabel', () => {
    it('returns correct Chinese labels', () => {
      expect(getTypeLabel(field({ type: 'button' }))).toBe('按钮')
      expect(getTypeLabel(field({ type: 'string' }))).toBe('字符串')
      expect(getTypeLabel(field({ type: 'number' }))).toBe('数字')
      expect(getTypeLabel(field({ type: 'boolean' }))).toBe('布尔')
      expect(getTypeLabel(field({ type: 'list' }))).toBe('列表')
      expect(getTypeLabel(field({ type: 'key_value' }))).toBe('键值对')
      expect(getTypeLabel(field({ type: 'table' }))).toBe('表格')
    })
  })

  describe('getSchemaButtonAction', () => {
    it('returns null when no action', () => {
      const result = getSchemaButtonAction('btn', field({}), 'plugin1')
      expect(result).toBeNull()
    })

    it('returns action when path is defined', () => {
      const result = getSchemaButtonAction(
        'btn',
        field({
          action: { path: '/api/test', label: 'Test', method: 'POST' },
        }),
        'plugin1'
      )
      expect(result).not.toBeNull()
      expect(result!.id).toBe('btn')
      expect(result!.path).toBe('/api/test')
      expect(result!.plugin).toBe('plugin1')
    })

    it('returns null when action path is empty', () => {
      const result = getSchemaButtonAction('btn', field({ action: { path: '' } }), 'plugin1')
      expect(result).toBeNull()
    })

    it('supports action.button as fallback', () => {
      const result = getSchemaButtonAction(
        'btn',
        field({
          button: { path: '/api/button', label: 'Button' },
        }),
        'plugin1'
      )
      expect(result).not.toBeNull()
      expect(result!.path).toBe('/api/button')
    })
  })

  describe('parseConfigText', () => {
    it('parses valid JSON object', () => {
      const result = parseConfigText('{"key": "value"}')
      expect(result).toEqual({ key: 'value' })
    })

    it('throws on array', () => {
      expect(() => parseConfigText('[1, 2, 3]')).toThrow('JSON 对象')
    })

    it('throws on primitive', () => {
      expect(() => parseConfigText('"string"')).toThrow('JSON 对象')
    })

    it('throws on invalid JSON', () => {
      expect(() => parseConfigText('{invalid}')).toThrow()
    })
  })

  describe('setConfigObjectToText', () => {
    it('converts object to formatted JSON', () => {
      const result = setConfigObjectToText({ key: 'value' })
      expect(JSON.parse(result)).toEqual({ key: 'value' })
      expect(result).toContain('\n')
    })
  })

  describe('isValidHttpUrl', () => {
    it('returns empty for valid URL', () => {
      expect(isValidHttpUrl('http://localhost:8080')).toBe('')
      expect(isValidHttpUrl('https://example.com')).toBe('')
    })

    it('returns error for invalid protocol', () => {
      expect(isValidHttpUrl('ftp://example.com')).toContain('http 或 https')
    })

    it('returns error for invalid URL', () => {
      expect(isValidHttpUrl('not-a-url')).toContain('有效的 URL')
    })
  })

  describe('validateSchemaFieldValue', () => {
    it('returns empty for button schema', () => {
      const result = validateSchemaFieldValue('btn', field({ type: 'button' }), 'x')
      expect(result).toBe('')
    })

    it('returns required error for null value', () => {
      const result = validateSchemaFieldValue(
        'name',
        field({ type: 'string', required: true }),
        null
      )
      expect(result).toBe('该字段为必填项')
    })

    it('validates string min length', () => {
      const result = validateSchemaFieldValue(
        'name',
        field({ type: 'string', constraints: { min_length: 5 } }),
        'abc'
      )
      expect(result).toContain('至少需要 5')
    })

    it('validates string max length', () => {
      const result = validateSchemaFieldValue(
        'name',
        field({ type: 'string', constraints: { max_length: 3 } }),
        'abcdef'
      )
      expect(result).toContain('最多允许 3')
    })

    it('validates URL format', () => {
      const result = validateSchemaFieldValue(
        'url',
        field({ type: 'string', format: 'url' }),
        'not-a-url'
      )
      expect(result).toContain('有效的 URL')
    })

    it('validates number range (ge)', () => {
      const result = validateSchemaFieldValue(
        'count',
        field({ type: 'integer', constraints: { ge: 10 } }),
        '5'
      )
      expect(result).toContain('不能小于 10')
    })

    it('validates number range (le)', () => {
      const result = validateSchemaFieldValue(
        'count',
        field({ type: 'integer', constraints: { le: 100 } }),
        '200'
      )
      expect(result).toContain('不能大于 100')
    })

    it('returns empty for valid value', () => {
      const result = validateSchemaFieldValue('name', field({ type: 'string' }), 'valid name')
      expect(result).toBe('')
    })
  })

  describe('collectSchemaFieldErrors', () => {
    it('returns errors for invalid config', () => {
      const errors = collectSchemaFieldErrors(
        [['name', field({ type: 'string', required: true })]],
        '{"name": ""}'
      )
      expect(errors).toHaveProperty('name')
    })

    it('returns empty for valid config', () => {
      const errors = collectSchemaFieldErrors(
        [['name', field({ type: 'string' })]],
        '{"name": "test"}'
      )
      expect(errors).toEqual({})
    })

    it('handles invalid JSON gracefully', () => {
      const errors = collectSchemaFieldErrors([['name', field({ type: 'string' })]], '{invalid')
      expect(errors).toEqual({})
    })
  })
})
