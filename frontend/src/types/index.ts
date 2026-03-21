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

export interface Account {
  id: number
  email: string
  provider: string
  last_sync: string | null
  created_at: string
}

export interface CalendarEvent {
  id: number
  source: string
  title: string
  description: string | null
  start_time: string
  end_time: string | null
  all_day: boolean
  location: string | null
  event_type: string | null
}

export interface SyncStatus {
  accounts: {
    email: string
    last_sync: string | null
    provider: string
  }[]
}

export interface CanvasConfig {
  id: number
  canvas_url: string
  status: 'active' | 'expired' | 'error'
  last_sync: string | null
}

export interface Task {
  id: number
  source: string
  title: string
  description: string | null
  course: string | null
  deadline: string | null
  estimated_minutes: number | null
  priority: number
  status: 'pending' | 'in_progress' | 'done' | 'skipped'
  grade_weight: number | null
  current_grade: string | null
}

export interface Grade {
  id: number
  course_id: number
  assignment_name: string
  score: string | null
  points_possible: string | null
  status: string
}

export interface Course {
  id: number
  canvas_course_id: string
  name: string
  code: string | null
  syllabus_url: string | null
  syllabus_text: string | null
  syllabus_file: string | null
  instructor: string | null
  schedule_info: string | null
  updated_at: string | null
  current_grade?: string | null
}
