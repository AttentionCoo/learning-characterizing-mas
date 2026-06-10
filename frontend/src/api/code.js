import request from '@/utils/request'

export const executeCodeAPI = (data) => request.post('/code/execute', data)

export const codeAssistAPI = (data) => request.post('/code/assist', data)
