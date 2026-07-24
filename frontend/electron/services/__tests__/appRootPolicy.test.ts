import { describe, expect, it } from 'vitest'

import { resolveAppRoot } from '../appRootPolicy'

describe('app root policy', () => {
  it('uses the executable directory for a packaged app even when NODE_ENV says development', () => {
    expect(
      resolveAppRoot(
        {
          isPackaged: true,
          getPath: () => 'C:\\Alpha\\AUTO-MAS-v6-Experimental-Alpha.exe',
        },
        { NODE_ENV: 'development' },
        'C:\\attacker-cwd'
      )
    ).toBe('C:\\Alpha')
  })

  it('keeps the working directory behavior for an unpackaged development launch', () => {
    expect(
      resolveAppRoot(
        {
          isPackaged: false,
          getPath: () => 'C:\\dev\\AUTO-MAS.exe',
        },
        { NODE_ENV: 'development' },
        'C:\\dev-worktree'
      )
    ).toBe('C:\\dev-worktree')
  })
})
