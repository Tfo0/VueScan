export type ProjectBaseRequestFuzzParamSource = 'query' | 'body'
export type ProjectBaseRequestBodyType = 'json' | 'form'

export interface ProjectBaseRequestFuzzParam {
  key: string
  sources: ProjectBaseRequestFuzzParamSource[]
  valueTypes: string[]
  sampleValues: string[]
  hitCount: number
  sampleUrlCount: number
}

export interface ProjectBaseRequestPreset {
  baseurl: string
  baseapi: string
  baseQuery: string
  baseBody: string
  baseBodyType: ProjectBaseRequestBodyType
  baseHeaders: string
  requestMethod: 'GET' | 'POST'
  fuzzParams: ProjectBaseRequestFuzzParam[]
}

export interface ProjectBaseRequestPresetEnvelope {
  seq: number
  preset: ProjectBaseRequestPreset
}
