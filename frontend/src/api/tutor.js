import request from '@/utils/request'
import { sseStreamRequest } from '@/utils/sseStream'

export const getTutorConversationsAPI = () => request.get('/tutor/conversations')

export const getTutorConversationHistoryAPI = (talkId) => request.get(`/tutor/conversation/${talkId}`)

export const deleteTutorConversationAPI = (talkId) => request.delete(`/tutor/conversation/${talkId}`)

export function tutorStreamAPI(params, onChunk, onThinking) {
  return sseStreamRequest('/api/tutor/chat', params, { onChunk, onThinking })
}
