import request from '@/utils/request'
import { sseStreamRequest } from '@/utils/sseStream'

export const getResourcesAPI = (params) => request.get('/resources', { params })

export const getResourceDetailAPI = (id) => request.get(`/resources/${id}`)

export const downloadResourceAPI = (id) => request.get(`/resources/${id}/download`)

export const deleteResourceAPI = (id) => request.delete(`/resources/${id}`)

export function resourceStreamAPI(url, params, onChunk, onThinking) {
  return sseStreamRequest(url, params, { onChunk, onThinking })
}
