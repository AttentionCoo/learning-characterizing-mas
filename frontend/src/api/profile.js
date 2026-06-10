import request from '@/utils/request'

export const getProfileAPI = () => request.get('/profile')

export const updateProfileDimensionsAPI = (data) => request.put('/profile/dimensions', data)

export const getProfileConversationsAPI = () => request.get('/profile/conversations')

export const getProfileConversationHistoryAPI = (talkId) => request.get(`/profile/conversation/${talkId}`)

export const deleteProfileConversationAPI = (talkId) => request.delete(`/profile/conversation/${talkId}`)

export function profileStreamAPI(params, onChunk, onThinking) {
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

    fetch('/api/profile/conversation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: token, token },
      body: JSON.stringify(params),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`请求失败: ${res.status}`)
        if (!res.body) throw new Error('ReadableStream不存在')
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
            .catch(safeReject)
        }
        read()
      })
      .catch(safeReject)
  })
}
