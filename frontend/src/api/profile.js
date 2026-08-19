import request from '@/utils/request'
import { sseStreamRequest } from '@/utils/sseStream'

export const getProfileAPI = () => request.get('/profile')

export const updateProfileDimensionsAPI = (data) => request.put('/profile/dimensions', data)

export function profileStreamAPI(params, onChunk, onThinking) {
  return sseStreamRequest('/api/profile/conversation', params, { onChunk, onThinking })
}
