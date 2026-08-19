import request from '@/utils/request'
import { sseStreamRequest } from '@/utils/sseStream'

export function tutorStreamAPI(params, onChunk, onThinking) {
  return sseStreamRequest('/api/tutor/chat', params, { onChunk, onThinking })
}
