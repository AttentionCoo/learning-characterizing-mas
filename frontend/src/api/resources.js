import request from '@/utils/request'

export const getResourcesAPI = (params) => request.get('/resources', { params })

export const getResourceDetailAPI = (id) => request.get(`/resources/${id}`)

export const downloadResourceAPI = (id) => request.get(`/resources/${id}/download`)

export const deleteResourceAPI = (id) => request.delete(`/resources/${id}`)

export const getResourceConversationsAPI = () => request.get('/resources/conversations')

export const getResourceConversationHistoryAPI = (talkId) => request.get(`/resources/conversation/${talkId}`)

export function resourceStreamAPI(url, params, onChunk, onThinking) {
  const token = localStorage.getItem('Synapse_MD_USER')
    ? JSON.parse(localStorage.getItem('Synapse_MD_USER')).token
    : ''

  return new Promise((resolve, reject) => {
    let fullAnswer = ''
    let realTalkId = null
    let finished = false

    function safeResolve(payload) {
      if (finished) return
      finished = true
      resolve(payload)
    }

    function safeReject(error) {
      if (finished) return
      finished = true
      reject(error)
    }

    function handleMessageBlock(block) {
      if (!block.trim()) return
      const lines = block.split(/\r?\n/)
      const dataLines = []
      for (const line of lines) {
        if (!line || line.startsWith(':')) continue
        if (line.startsWith('event:')) continue
        if (line.startsWith('id:')) continue
        if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
      }
      if (!dataLines.length) return
      try {
        const data = JSON.parse(dataLines.join('\n').trim())
        const type = data.type
        if (data.talkId) realTalkId = data.talkId
        if (type === 'init') return
        if (type === 'node_start' && onThinking) {
          onThinking({ step: '', title: data.label || '', content: '' })
          return
        }
        if (type === 'thinking' && onThinking) {
          onThinking({ step: data.step || '', title: data.title || '', content: data.content || '' })
          return
        }
        if (type === 'chunk') {
          fullAnswer += data.content || ''
          if (onChunk) onChunk(data.content || '')
          return
        }
        if (type === 'result') {
          fullAnswer += data.content || ''
          if (onChunk) onChunk(data.content || '')
          return
        }
        if (type === 'done') {
          safeResolve({ data: { talkId: realTalkId, content: fullAnswer } })
          return
        }
        if (type === 'error') {
          safeReject(new Error(data.message || '流式响应错误'))
        }
      } catch (e) {
        console.error('解析SSE块失败', e)
      }
    }

    const controller = new AbortController()
    const timeoutId = setTimeout(() => {
      controller.abort()
      safeReject(new Error('请求超时，请稍后重试'))
    }, 120000)

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: token, token },
      body: JSON.stringify(params),
      signal: controller.signal,
    })
      .then((res) => {
        clearTimeout(timeoutId)
        if (!res.ok) {
          if (res.status === 401 || res.status === 403) {
            safeReject(new Error('未登录或登录已过期'))
          } else if (res.status === 404) {
            safeReject(new Error('资源生成接口不存在，请检查后端服务配置'))
          } else if (res.status >= 500) {
            safeReject(new Error(`服务器内部错误 (${res.status})，请稍后重试`))
          } else {
            safeReject(new Error(`请求失败: ${res.status} ${res.statusText}`))
          }
          return
        }
        if (!res.body) {
          safeReject(new Error('响应体为空'))
          return
        }
        const reader = res.body.getReader()
        const decoder = new TextDecoder('utf-8')
        let buffer = ''
        function read() {
          reader
            .read()
            .then(({ value, done }) => {
              if (done) {
                buffer += decoder.decode()
                while (buffer.includes('\n\n')) {
                  const idx = buffer.indexOf('\n\n')
                  handleMessageBlock(buffer.slice(0, idx))
                  buffer = buffer.slice(idx + 2)
                }
                if (!finished) safeResolve({ data: { talkId: realTalkId, content: fullAnswer } })
                return
              }
              buffer += decoder.decode(value, { stream: true })
              buffer = buffer.replace(/\r\n/g, '\n')
              while (buffer.includes('\n\n')) {
                const idx = buffer.indexOf('\n\n')
                handleMessageBlock(buffer.slice(0, idx))
                buffer = buffer.slice(idx + 2)
                if (finished) {
                  reader.cancel()
                  return
                }
              }
              read()
            })
            .catch((err) => {
              clearTimeout(timeoutId)
              if (err.name === 'AbortError') {
                safeReject(new Error('请求被取消或超时'))
              } else {
                safeReject(err)
              }
            })
        }
        read()
      })
      .catch((err) => {
        clearTimeout(timeoutId)
        if (err.name === 'AbortError') {
          safeReject(new Error('请求被取消或超时'))
        } else if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
          safeReject(new Error('网络连接失败，请检查后端服务是否启动'))
        } else {
          safeReject(err)
        }
      })
  })
}
