import { useMemo, useState, useCallback } from 'react'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import { useEvents } from '../hooks/useEvents'
import { useSchedule } from '../hooks/useSchedule'
import BlockDetail from './BlockDetail'
import type { CalendarEvent, ScheduleBlock } from '../types'

interface CalendarViewProps {
  mode: 'day' | 'week'
}

const SOURCE_COLORS: Record<string, string> = {
  gcal: '#22c55e',
  gmail: '#3b82f6',
  canvas: '#f59e0b',
  manual: '#a855f7',
}

const BLOCK_COLORS: Record<string, string> = {
  study: '#3b82f6',
  meeting: '#22c55e',
  rest: '#f59e0b',
  personal: '#a855f7',
  buffer: '#6b7280',
}

function toFullCalendarEvent(event: CalendarEvent) {
  return {
    id: `event-${event.id}`,
    title: event.title,
    start: event.start_time,
    end: event.end_time || undefined,
    allDay: event.all_day,
    backgroundColor: SOURCE_COLORS[event.source] || '#6b7280',
    borderColor: SOURCE_COLORS[event.source] || '#6b7280',
    extendedProps: { type: 'event', source: event.source },
  }
}

function blockToFullCalendar(block: ScheduleBlock) {
  const date = block.date
  return {
    id: `block-${block.id}`,
    title: `${block.block_type.charAt(0).toUpperCase() + block.block_type.slice(1)}${block.ai_reason ? `: ${block.ai_reason}` : ''}`,
    start: `${date}T${block.start_time}:00`,
    end: `${date}T${block.end_time}:00`,
    backgroundColor: block.status === 'completed' ? '#374151' : (BLOCK_COLORS[block.block_type] || '#6b7280'),
    borderColor: block.status === 'completed' ? '#4b5563' : (BLOCK_COLORS[block.block_type] || '#6b7280'),
    textColor: block.status === 'completed' ? '#9ca3af' : '#ffffff',
    extendedProps: { type: 'block', block },
  }
}

export default function CalendarView({ mode }: CalendarViewProps) {
  const initialView = mode === 'day' ? 'timeGridDay' : 'timeGridWeek'
  const today = new Date().toISOString().split('T')[0]
  const { events } = useEvents()
  const { schedule, updateBlock, triggerReplan } = useSchedule(today)
  const [selectedBlock, setSelectedBlock] = useState<ScheduleBlock | null>(null)

  const calendarEvents = useMemo(() => {
    const eventItems = events.map(toFullCalendarEvent)
    const blockItems = (schedule?.blocks || []).map(blockToFullCalendar)
    return [...eventItems, ...blockItems]
  }, [events, schedule])

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleEventClick = useCallback((info: any) => {
    const props = info.event.extendedProps
    if (props.type === 'block' && props.block) {
      setSelectedBlock(props.block as ScheduleBlock)
    }
  }, [])

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleEventDrop = useCallback(async (info: any) => {
    const props = info.event.extendedProps
    if (props.type !== 'block' || !props.block) {
      info.revert()
      return
    }
    const block = props.block as ScheduleBlock
    try {
      const newStart = info.event.start?.toTimeString().slice(0, 5) || block.start_time
      const newEnd = info.event.end?.toTimeString().slice(0, 5) || block.end_time
      await updateBlock(block.id, { start_time: newStart, end_time: newEnd })
      await triggerReplan()
    } catch {
      info.revert()
    }
  }, [updateBlock, triggerReplan])

  const handleComplete = useCallback(async (blockId: number) => {
    await updateBlock(blockId, { status: 'completed' })
    setSelectedBlock(null)
  }, [updateBlock])

  const handleSkip = useCallback(async (blockId: number) => {
    await updateBlock(blockId, { status: 'skipped' })
    setSelectedBlock(null)
  }, [updateBlock])

  return (
    <div className="h-full">
      <FullCalendar
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView={initialView}
        headerToolbar={{
          left: 'prev,next today',
          center: 'title',
          right: 'timeGridDay,timeGridWeek',
        }}
        editable={mode === 'day'}
        selectable={mode === 'day'}
        nowIndicator={true}
        slotMinTime="06:00:00"
        slotMaxTime="24:00:00"
        height="100%"
        events={calendarEvents}
        eventClick={handleEventClick}
        eventDrop={handleEventDrop}
      />

      {selectedBlock && (
        <BlockDetail
          block={selectedBlock}
          onClose={() => setSelectedBlock(null)}
          onComplete={handleComplete}
          onSkip={handleSkip}
        />
      )}
    </div>
  )
}
