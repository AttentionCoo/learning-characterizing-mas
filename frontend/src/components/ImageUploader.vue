<template>
  <div class="image-uploader">
    <!-- 已上传图片列表 -->
    <div class="uploaded-images" v-if="images.length > 0">
      <div
        v-for="(img, idx) in images"
        :key="idx"
        class="image-preview-item"
        @click="$emit('preview', idx)"
      >
        <img :src="img" alt="预览" />
        <button class="remove-btn" @click.stop="removeImage(idx)" title="移除">✕</button>
        <div class="image-index">{{ idx + 1 }}</div>
      </div>
    </div>

    <!-- 上传区域 -->
    <div
      class="upload-zone"
      :class="{ dragging: isDragging, 'has-images': images.length > 0 }"
      @drop.prevent="onDrop"
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @click="triggerFileInput"
    >
      <input
        ref="fileInputRef"
        type="file"
        accept="image/*,.dcm,.dicom"
        multiple
        @change="onFileChange"
        style="display: none"
      />
      <div class="upload-hint">
        <span class="upload-icon">{{ images.length > 0 ? '➕' : '📁' }}</span>
        <p>{{ images.length > 0 ? '添加更多影像' : '点击或拖拽上传医学影像' }}</p>
        <p class="upload-sub">支持 JPG/PNG/WebP/DICOM(.dcm) · 单文件最大10MB</p>
      </div>
    </div>

    <!-- 图片类型提示 -->
    <div class="type-info" v-if="detectedType && images.length > 0">
      <span class="type-badge">{{ typeLabels[detectedType] || detectedType }}</span>
      <span class="type-desc">已自动检测影像类型，可手动选择其他类型</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { compressImage } from '@/utils/imageCompress'

const props = defineProps({
  images: { type: Array, default: () => [] },
  maxCount: { type: Number, default: 5 },
  maxSizeMB: { type: Number, default: 10 },
})

const emit = defineEmits(['update:images', 'preview', 'type-detected'])

const fileInputRef = ref(null)
const isDragging = ref(false)
const detectedType = ref('')

const typeLabels = {
  neuroimaging_ct: '头部CT',
  neuroimaging_mri: '头部MRI',
  neuroimaging_angiography: '脑血管造影',
  pathology_slide: '病理切片',
  ecg_waveform: '心电图/脑电图',
  clinical_photo: '临床照片',
  lab_report: '检验报告',
  radiology_report: '影像报告',
  medical_illustration: '医学图解',
  courseware_image: '课件资料',
}

function triggerFileInput() {
  fileInputRef.value?.click()
}

function removeImage(idx) {
  const newImages = [...props.images]
  newImages.splice(idx, 1)
  emit('update:images', newImages)
}

async function processFiles(files) {
  const remaining = props.maxCount - props.images.length
  if (remaining <= 0) return

  const newImages = [...props.images]

  for (let i = 0; i < Math.min(files.length, remaining); i++) {
    const file = files[i]

    // 检查文件类型
    const isDICOM = file.name?.toLowerCase().endsWith('.dcm') ||
                    file.name?.toLowerCase().endsWith('.dicom')
    const isImage = file.type?.startsWith('image/')

    if (!isDICOM && !isImage) continue

    // 检查文件大小
    if (file.size > props.maxSizeMB * 1024 * 1024) {
      console.warn(`文件 ${file.name} 超过${props.maxSizeMB}MB限制，跳过`)
      continue
    }

    try {
      const base64 = await compressImage(file)
      newImages.push(base64)
    } catch (err) {
      console.error(`文件 ${file.name} 处理失败:`, err)
    }
  }

  emit('update:images', newImages)

  // 简单类型检测
  if (newImages.length > 0 && !detectedType.value) {
    detectImageType()
  }
}

function onFileChange(e) {
  const files = e.target.files
  if (files?.length) processFiles(files)
  // 重置input以允许重复选择同一文件
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function onDrop(e) {
  isDragging.value = false
  const files = e.dataTransfer?.files
  if (files?.length) processFiles(files)
}

function detectImageType() {
  emit('type-detected', 'courseware_image')
}
</script>

<style scoped>
.image-uploader { }

.uploaded-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.image-preview-item {
  position: relative;
  width: 80px;
  height: 80px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 2px solid var(--color-border);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.image-preview-item:hover {
  border-color: var(--color-primary);
  box-shadow: var(--glow-primary);
  transform: translateY(-1px);
}
.image-preview-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.remove-btn {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: none;
  background: rgba(15, 23, 42, 0.65);
  color: #fff;
  font-size: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}
.remove-btn:hover {
  background: var(--color-red);
  transform: scale(1.1);
}
.image-index {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 2px 0;
  background: rgba(15, 23, 42, 0.55);
  color: #fff;
  font-size: 10px;
  text-align: center;
  backdrop-filter: blur(4px);
}

.upload-zone {
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-lg);
  padding: 22px;
  text-align: center;
  cursor: pointer;
  transition: all var(--transition-normal);
  background: var(--color-bg-base);
}
.upload-zone:hover {
  border-color: var(--color-primary);
  background: var(--color-active-bg);
  transform: translateY(-1px);
}
.upload-zone.dragging {
  border-color: var(--color-primary);
  background: var(--color-active-bg);
  box-shadow: var(--glow-primary);
  border-style: solid;
}
.upload-zone.has-images { padding: 14px; }
.upload-icon { font-size: 1.5rem; }
.upload-hint p { margin: 4px 0; color: var(--color-text-medium); font-size: 0.88rem; }
.upload-sub { font-size: 0.74rem !important; color: var(--color-text-weak) !important; }

.type-info { margin-top: 8px; display: flex; align-items: center; gap: 8px; font-size: 0.83rem; }
.type-badge {
  padding: 3px 12px;
  background: var(--color-active-bg);
  color: var(--color-text-label);
  border-radius: var(--radius-pill);
  font-size: 0.78rem;
  font-weight: 500;
  border: 1px solid var(--color-border-light);
}
.type-desc { color: var(--color-text-weak); }
</style>
