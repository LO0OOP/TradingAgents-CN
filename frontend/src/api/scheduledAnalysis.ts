/**
 * 定时分析任务组 API
 */
import { request, type ApiResponse } from './request'

export interface ScheduledGroup {
  id: string
  group_id: string
  name: string
  enabled: boolean
  weekdays: number[]
  time: string
  symbols: string[]
  parameters: Record<string, any>
  created_at?: string
  updated_at?: string
  last_run_at?: string
}

export interface GroupPayload {
  name: string
  enabled?: boolean
  weekdays: number[]
  time: string
  symbols: string[]
  parameters: Record<string, any>
}

export const scheduledAnalysisApi = {
  listGroups(): Promise<ApiResponse<ScheduledGroup[]>> {
    return request.get('/api/scheduled-analysis/groups')
  },

  createGroup(data: GroupPayload): Promise<ApiResponse<ScheduledGroup>> {
    return request.post('/api/scheduled-analysis/groups', data)
  },

  updateGroup(groupId: string, data: Partial<GroupPayload>): Promise<ApiResponse<ScheduledGroup>> {
    return request.put(`/api/scheduled-analysis/groups/${groupId}`, data)
  },

  deleteGroup(groupId: string): Promise<ApiResponse<any>> {
    return request.delete(`/api/scheduled-analysis/groups/${groupId}`)
  },

  toggleGroup(groupId: string): Promise<ApiResponse<ScheduledGroup>> {
    return request.post(`/api/scheduled-analysis/groups/${groupId}/toggle`)
  },

  runGroup(groupId: string): Promise<ApiResponse<any>> {
    return request.post(`/api/scheduled-analysis/groups/${groupId}/run`)
  }
}