import { defineConfig } from '@hey-api/openapi-ts'

export default defineConfig({
  input: './openapi.json',
  output: './src/api/generated',
  client: 'legacy/axios',
  useOptions: false,
  exportCore: true,
  exportServices: true,
  exportModels: true,
  exportSchemas: false,
})
