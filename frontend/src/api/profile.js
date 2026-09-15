import request from '@/utils/request'
import { sseStreamRequest } from '@/utils/sseStream'

export const getProfileAPI = () => request.get('/profile')

export const updateProfileDimensionsAPI = (data) => request.put('/profile/dimensions', data)

/** 清空当前用户的学习画像 */
export const clearProfileAPI = () => request.delete('/profile')

export function profileStreamAPI(params, onChunk, onThinking) {
  return sseStreamRequest('/api/profile/conversation', params, { onChunk, onThinking })
}
