// imageCompress.js — 前端图片压缩工具
// 宽/高超过 maxWidth 时等比缩放，输出 JPEG Base64 data URL
// DICOM 文件跳过画布压缩，直接读取为 Base64 原始数据

const MAX_FILE_SIZE = 10 * 1024 * 1024  // 10MB（单张上限，与 XF-Xinghuo VL 要求一致）
const MAX_WIDTH = 2048                   // 超过此尺寸时等比缩放
const JPEG_QUALITY = 0.85               // JPEG 压缩质量

// DICOM 文件扩展名和 MIME 类型
const DICOM_EXTENSIONS = ['.dcm', '.dicom']
const DICOM_MIME_TYPES = ['application/dicom', 'application/octet-stream']

/**
 * 判断文件是否为 DICOM 格式
 * @param {File} file
 * @returns {boolean}
 */
function isDICOMFile(file) {
  const name = (file.name || '').toLowerCase()
  const type = (file.type || '').toLowerCase()
  return DICOM_EXTENSIONS.some(ext => name.endsWith(ext)) ||
         DICOM_MIME_TYPES.some(mime => type === mime)
}

/**
 * 将文件读取为 Base64 字符串（不压缩，用于 DICOM 等非图片格式）
 * @param {File} file - 文件对象
 * @returns {Promise<string>} data URL（data:application/dicom;base64,... 或 data:...;base64,...）
 */
export function readFileAsBase64(file) {
  if (file.size > MAX_FILE_SIZE) {
    throw new Error(`文件大小不能超过 10MB（当前 ${(file.size / 1024 / 1024).toFixed(1)}MB）`)
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = reader.result
      if (typeof dataUrl === 'string') {
        resolve(dataUrl)
      } else {
        reject(new Error('文件读取失败'))
      }
    }
    reader.onerror = () => reject(new Error('文件读取失败，请重试'))
    reader.readAsDataURL(file)
  })
}

/**
 * 统一的文件处理入口：DICOM → 原始 Base64，普通图片 → 压缩 Base64
 * @param {File} file - 文件对象
 * @returns {Promise<{ dataUrl: string, isDICOM: boolean }>}
 */
export async function processFile(file) {
  if (isDICOMFile(file)) {
    const dataUrl = await readFileAsBase64(file)
    // 确保 DICOM 文件有正确的 data URL 前缀
    // FileReader 对 .dcm 可能返回 data:application/octet-stream;base64,...
    // 或空的 MIME type，后端会自行判断
    return { dataUrl, isDICOM: true }
  }
  // 普通图片走压缩路径
  const dataUrl = await compressImage(file)
  return { dataUrl, isDICOM: false }
}

/**
 * 压缩图片并返回 Base64 data URL
 * @param {File} file - 图片文件（JPG/PNG/WebP）
 * @returns {Promise<string>} data URL（data:image/...;base64,...）
 * @throws {Error} 文件过大或格式不支持时抛出
 */
export async function compressImage(file) {
  if (file.size > MAX_FILE_SIZE) {
    throw new Error(`图片大小不能超过 10MB（当前 ${(file.size / 1024 / 1024).toFixed(1)}MB）`)
  }

  const supportedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
  if (!supportedTypes.includes(file.type)) {
    // DICOM 等非图片格式不在此处理
    throw new Error(`不支持的图片格式: ${file.type || file.name}（仅支持 JPG、PNG、WebP）`)
  }

  return new Promise((resolve, reject) => {
    const img = new Image()
    const objectUrl = URL.createObjectURL(file)

    img.onload = () => {
      URL.revokeObjectURL(objectUrl)

      const { width: origW, height: origH } = img
      let targetW = origW
      let targetH = origH

      // 等比缩放：长边超过 MAX_WIDTH 时缩小
      if (origW > MAX_WIDTH || origH > MAX_WIDTH) {
        const ratio = MAX_WIDTH / Math.max(origW, origH)
        targetW = Math.round(origW * ratio)
        targetH = Math.round(origH * ratio)
      }

      const canvas = document.createElement('canvas')
      canvas.width = targetW
      canvas.height = targetH
      const ctx = canvas.getContext('2d')
      ctx.drawImage(img, 0, 0, targetW, targetH)

      // PNG 转 JPEG（透明背景填白）以减小体积
      if (file.type === 'image/png') {
        const imageData = ctx.getImageData(0, 0, targetW, targetH)
        const data = imageData.data
        for (let i = 3; i < data.length; i += 4) {
          if (data[i] < 255) {
            // 半透明像素：与白色背景合成
            const alpha = data[i] / 255
            data[i - 3] = Math.round(data[i - 3] * alpha + 255 * (1 - alpha))
            data[i - 2] = Math.round(data[i - 2] * alpha + 255 * (1 - alpha))
            data[i - 1] = Math.round(data[i - 1] * alpha + 255 * (1 - alpha))
            data[i] = 255
          }
        }
        ctx.putImageData(imageData, 0, 0)
      }

      resolve(canvas.toDataURL('image/jpeg', JPEG_QUALITY))
    }

    img.onerror = () => {
      URL.revokeObjectURL(objectUrl)
      reject(new Error('图片加载失败，请重新选择'))
    }

    img.src = objectUrl
  })
}
