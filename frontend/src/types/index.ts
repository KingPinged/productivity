export interface ScheduleBlock {
  id: number
  task_id: number | null
  date: string
  start_time: string
  end_time: string
  block_type: 'study' | 'meeting' | 'rest' | 'personal' | 'buffer'
  status: 'scheduled' | 'active' | 'completed' | 'skipped' | 'rescheduled'
  ai_reason: string | null
}

export interface DaySchedule {
  date: string
  blocks: ScheduleBlock[]
}

export interface Preferences {
  [key: string]: string
}
