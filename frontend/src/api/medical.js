/**
 * 医学多模态 API 模块
 * Medical Multimodal API Module
 */
import request from '@/utils/request'

const MODEL_BASE = '/model/medical'

/**
 * 医学影像结构化分析（非流式）
 * @param {Object} params - { images: string[], question: string, all_info?: string, expected_image_type?: string }
 * @returns {Promise} - { findings, pubmed_evidence, local_evidence, analysis_text }
 */
export function analyzeMedicalImageAPI(params) {
  return request.post(`${MODEL_BASE}/analyze-image`, params)
}

/**
 * 多模态病例综合分析（SSE 流式）
 * @param {Object} params - { talkId?, message: string, images: string[], case_type?: string, include_evidence?: boolean }
 * @param {Object} callbacks - { onInit, onNodeStart, onToken, onNodeDone, onDone, onError }
 * @returns {Promise} - talkId
 */
export async function analyzeMedicalCaseAPI(params, callbacks = {}) {
  const { onInit, onNodeStart, onToken, onNodeDone, onDone, onError } = callbacks
  try {
    const response = await fetch('/api/model/medical/analyze-case', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('token')}`,
      },
      body: JSON.stringify(params),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let talkId = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed) continue

        try {
          const event = JSON.parse(trimmed)

          if (event.type === 'init') {
            talkId = event.talkId
            onInit?.(event)
          } else if (event.type === 'node_start') {
            onNodeStart?.(event)
          } else if (event.type === 'token') {
            onToken?.(event.content)
          } else if (event.type === 'node_done') {
            onNodeDone?.(event)
          } else if (event.type === 'done') {
            onDone?.(event)
          } else if (event.type === 'error') {
            onError?.(event)
          }
        } catch {
          // skip malformed JSON
        }
      }
    }
    return talkId
  } catch (error) {
    onError?.(error)
    throw error
  }
}

/**
 * 多图对比分析
 * @param {Object} params - { images: string[], question?: string, all_info?: string }
 * @returns {Promise} - MultiImageComparison
 */
export function compareMedicalImagesAPI(params) {
  return request.post(`${MODEL_BASE}/compare-images`, params)
}

/**
 * DICOM元数据提取
 * @param {string} imageBase64 - Base64 编码的 DICOM 数据
 * @returns {Promise} - DICOMMetadata
 */
export function extractDICOMMetadataAPI(imageBase64) {
  return request.post(`${MODEL_BASE}/dicom-metadata`, { image: imageBase64 })
}

/**
 * 检验报告OCR提取
 * @param {Object} params - { images: string[], question?: string }
 * @returns {Promise} - LabReport
 */
export function extractLabReportAPI(params) {
  return request.post(`${MODEL_BASE}/ocr/lab-report`, params)
}

/**
 * 处方OCR提取
 * @param {Object} params - { images: string[], question?: string }
 * @returns {Promise} - PrescriptionInfo[]
 */
export function extractPrescriptionAPI(params) {
  return request.post(`${MODEL_BASE}/ocr/prescription`, params)
}

/**
 * DICOM → PNG 预览转换
 * 将 DICOM Base64 数据转换为 PNG 格式用于前端缩略图预览
 * @param {string} imageBase64 - Base64 编码的 DICOM 数据
 * @returns {Promise} - { image: string } PNG base64 data URL
 */
export function dicomToPngAPI(imageBase64) {
  return request.post(`${MODEL_BASE}/dicom-to-png`, { images: [imageBase64] })
}
