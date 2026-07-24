declare module 'markdown-it' {
  export interface MarkdownItOptions {
    html?: boolean
    xhtmlOut?: boolean
    breaks?: boolean
    langPrefix?: string
    linkify?: boolean
    typographer?: boolean
    quotes?: string | string[]
  }

  export default class MarkdownIt {
    constructor(options?: MarkdownItOptions)
    render(source: string, env?: unknown): string
    renderInline(source: string, env?: unknown): string
  }
}
