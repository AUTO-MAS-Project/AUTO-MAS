import test from 'node:test'
import assert from 'node:assert/strict'
import { shanghai, sameRegion, opening, handoff } from '../src/views/taskboard/bannerWatch.ts'

test('Shanghai midnight rollover and unavailable times', () => {
  assert.match(shanghai('2026-11-19T17:00:00Z', 'en-US', '?'), /Nov 20, 2026.*01:00/)
  assert.equal(shanghai(null, 'en-US', '?'), '?')
})

test('maintenance waits for confirmed opening and tbd ignores estimated dates', () => {
  const banner = { start_mode: 'after_maintenance', starts_at: 'estimate' }
  const identity = v => v
  assert.equal(opening(banner, identity, identity), 'after')
  assert.equal(opening({ ...banner, start_mode: 'tbd' }, identity, identity), 'tbd')
  assert.equal(
    opening({ ...banner, confirmed_open_at: 'confirmed' }, identity, identity),
    'confirmed'
  )
})

test('subscriptions match both game and server', () => {
  const r = { game: 'endfield', server: 'cn' }
  assert.ok(sameRegion(r, { ...r }))
  assert.ok(!sameRegion(r, { ...r, server: 'jp' }))
  assert.ok(!sameRegion(r, { ...r, game: 'arknights' }))
})

test('absent, failed and disconnected bridges copy the exact edited request', async () => {
  const prompt = 'Edited request\nincluding notes & <data>'
  for (const bridge of [
    undefined,
    async () => ({ status: 'failed' }),
    async () => ({ status: 'unavailable' }),
    async () => {
      throw Error()
    },
  ]) {
    const copies = []
    assert.equal((await handoff(prompt, bridge, async text => copies.push(text))).message, 'copied')
    assert.deepEqual(copies, [prompt])
  }
  assert.equal(
    (
      await handoff(prompt, undefined, async () => {
        throw Error()
      })
    ).message,
    'copyFailed'
  )
})

test('direct result and busy replies leave clipboard untouched', async () => {
  let copies = 0
  const copy = async () => {
    copies++
  }
  assert.deepEqual(
    await handoff('reviewed', async text => ({ status: 'ok', analysis: text }), copy),
    { message: 'analysis', analysis: 'reviewed' }
  )
  assert.equal((await handoff('x', async () => ({ status: 'busy' }), copy)).message, 'busy')
  assert.equal(copies, 0)
})
