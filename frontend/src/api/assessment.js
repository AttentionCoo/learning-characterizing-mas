import request from '@/utils/request'
import { sseStreamRequest } from '@/utils/sseStream'

export const getAssessmentReportsAPI = (params) => request.get('/evaluation/reports', { params })

export const getAssessmentReportDetailAPI = (id) => request.get(`/evaluation/reports/${id}`)

export const getAssessmentReportAPI = (params) => request.get('/evaluation/report', { params })

export const submitBehaviorAPI = (data) => request.post('/evaluation/behavior', data)

export const optimizeLearningPathAPI = (data) => request.post('/evaluation/optimize', data)

export function assessmentStreamAPI(params, onChunk, onThinking) {
  return sseStreamRequest('/api/evaluation/generate', params, { onChunk, onThinking })
}
