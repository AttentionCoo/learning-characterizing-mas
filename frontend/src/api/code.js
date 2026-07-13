import request from '@/utils/request'
import { sseStreamRequest } from '@/utils/sseStream'

export const executeCodeAPI = (data) => request.post('/code/execute', data)

export function codeAssistStreamAPI(params, onChunk, onThinking, options = {}) {
  return sseStreamRequest('/api/code/assist', params, { onChunk, onThinking, ...options })
}
