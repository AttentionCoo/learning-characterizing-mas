import request from '@/utils/request'
import { sseStreamRequest } from '@/utils/sseStream'

export const getLearningPathsAPI = (params) => request.get('/learning-path', { params })

export const getLearningPathDetailAPI = (pathId) => request.get(`/learning-path/${pathId}`)

export async function getLearningPathAPI() {
  const listRes = await getLearningPathsAPI()
  const firstPath = listRes.data?.records?.[0]
  if (!firstPath?.pathId) return { ...listRes, data: null }
  return getLearningPathDetailAPI(firstPath.pathId)
}

export const updateTaskProgressAPI = (taskId, data) => request.put(`/learning-path/tasks/${taskId}/progress`, data)

export const getRecommendationsAPI = (params) => request.get('/learning-path/recommendations', { params })

export function learningPathStreamAPI(params, onChunk, onThinking) {
  return sseStreamRequest('/api/learning-path/generate', params, { onChunk, onThinking })
}
