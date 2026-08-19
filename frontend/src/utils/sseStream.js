/**
 * SSE 流式请求公共实现。
 *
 * 供 profile / resources / tutor / assessment / learningPath 五个 API 模块共用，
 * 统一处理：SSE 块解析、thinking/node_start 事件、超时中断、错误分类。
 *
 * resolve 结构：{ data: { talkId, content, profileDimensions } }
 * profileDimensions 仅画像构建场景的 done 事件携带，其余场景为 null。
 */
export function mergeStreamContent(current, type, incoming) {
  const content = incoming || ''
  return type === 'replace' ? content : `${current || ''}${content}`
}

export function sseStreamRequest(url, params, { onChunk, onThinking, timeout = 300000, signal: externalSignal } = {}) {
  const token = localStorage.getItem('Synapse_MD_USER')
    ? JSON.parse(localStorage.getItem('Synapse_MD_USER')).token
    : ''

  return new Promise((resolve, reject) => {
    let fullAnswer = ''
    let realTalkId = null
    let profileDimensions = null
    let finished = false

    function safeResolve() {
      if (finished) return
      finished = true
      resolve({ data: { talkId: realTalkId, content: fullAnswer, profileDimensions } })
    }

    function safeReject(error) {
      if (finished) return
      finished = true
      reject(error)
    }

    function handleMessageBlock(block) {
      if (finished) return
      if (!block.trim()) return
      console.log('[sseStream] raw block:', block.slice(0, 200))
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
          const trace = {
            phase: 'start',
            step: data.node || '',
            title: data.label || '',
            content: '',
            sources: [],
          }
          console.info('[AI 推理]', trace.title)
          onThinking(trace)
          return
        }
        if (type === 'thinking' && onThinking) {
          const src = data.thinking || data
          const trace = {
            phase: 'progress',
            step: src.step || '',
            title: src.title || '',
            content: src.content || '',
            sources: Array.isArray(src.sources) ? src.sources : [],
          }
          console.info('[AI 推理]', trace.title)
          onThinking(trace)
          return
        }
        if (type === 'node_done' && onThinking) {
          const trace = {
            phase: 'done',
            step: data.node || '',
            title: data.title || data.summary || '步骤完成',
            content: data.content || data.summary || '',
            sources: Array.isArray(data.sources) ? data.sources : [],
          }
          console.info('[AI 推理完成]', trace.title)
          if (trace.sources.length) {
            console.table(trace.sources.map(source => ({
              指南: source.guide,
              页码: source.page,
            })))
          }
          onThinking(trace)
          return
        }
        if (type === 'debate' && onThinking) {
          const trace = {
            phase: 'debate',
            step: 'debate',
            title: '多专家辩论与仲裁',
            content: '',
            sources: [],
            debate: {
              rounds: data.rounds || 0,
              history: Array.isArray(data.history) ? data.history : [],
              arbitration: data.arbitration || '',
            },
          }
          console.info('[AI 辩论]', `${trace.debate.rounds} 条辩论记录`)
          onThinking(trace)
          return
        }
        if (type === 'experts' && onThinking) {
          const trace = {
            phase: 'experts',
            step: data.node || 'reason',
            title: `多专家协同（${(data.active_experts || []).length} 位）`,
            content: '',
            sources: [],
            experts: {
              active: Array.isArray(data.active_experts) ? data.active_experts : [],
              advices: Array.isArray(data.advices) ? data.advices : [],
              debateRounds: data.debate_rounds || 0,
              arbitration: data.arbitration || '',
              selectionReason: data.selection_reason || '',
            },
          }
          console.info('[AI 专家发言]', `${trace.experts.active.length} 位专家，${trace.experts.advices.length} 条发言`)
          onThinking(trace)
          return
        }
        if (type === 'agent_msg' && onThinking) {
          const trace = {
            phase: 'agent_msg',
            step: data.node || 'reason',
            title: `专家对话：${data.from || ''} → ${data.to === '__all__' ? '全体' : (data.to || '')}`,
            content: '',
            sources: [],
            messages: [{
              from: data.from || '',
              to: data.to || '',
              round: data.round || 0,
              kind: data.kind || '',
              content: data.content || '',
            }],
          }
          console.info('[AI 专家对话]', `${data.from} → ${data.to} [${data.kind}]`)
          onThinking(trace)
          return
        }
        if (type === 'blackboard' && onThinking) {
          const trace = {
            phase: 'blackboard',
            step: data.node || 'reason',
            title: '专家会诊黑板',
            content: '',
            sources: [],
            blackboard: {
              entries: Array.isArray(data.entries) ? data.entries : [],
              convergence: data.convergence || '',
              arbitration: data.arbitration || '',
            },
          }
          console.info('[AI 会诊黑板]', `${trace.blackboard.entries.length} 条发现`)
          onThinking(trace)
          return
        }
        if (type === 'chunk' || type === 'result' || type === 'token' || type === 'replace') {
          const content = data.content || ''
          const replace = type === 'replace'
          fullAnswer = mergeStreamContent(fullAnswer, type, content)
          if (onChunk) onChunk(content, { replace })
          console.log('[sseStream] chunk received, type:', type, 'len:', (data.content || '').length, 'preview:', (data.content || '').slice(0, 80))
          return
        }
        if (type === 'done') {
          if (data.profile_dimensions) profileDimensions = data.profile_dimensions
          console.log('[sseStream] done event, fullAnswer len:', fullAnswer.length, 'preview:', fullAnswer.slice(0, 100))
          safeResolve()
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
    }, timeout)

    if (externalSignal) {
      if (externalSignal.aborted) {
        safeReject(new Error('请求被取消'))
        return
      }
      externalSignal.addEventListener('abort', () => {
        controller.abort()
        clearTimeout(timeoutId)
        safeReject(new Error('请求被取消'))
      }, { once: true })
    }

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
            safeReject(new Error('接口不存在，请检查后端服务配置'))
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
                safeResolve()
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
