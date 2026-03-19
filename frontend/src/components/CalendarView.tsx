import { useMemo } from 'react'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import { useEvents } from '../hooks/useEvents'
import type { CalendarEvent } from '../types'

interface CalendarViewProps {
  mode: 'day' | 'week'
}

const SOURCE_COLORS: Record<string, string> = {
  gcal: '#22c55e',
  gmail: '#3b82f6',
  canvas: '#f59e0b',
  manual: '#a855f7',
}

function toFullCalendarEvent(event: CalendarEvent) {
  return {
    id: String(event.id),
    title: event.title,
    start: event.start_time,
    end: event.end_time || undefined,
    allDay: event.all_day,
    backgroundColor: SOURCE_COLORS[event.source] || '#6b7280',
    borderColor: SOURCE_COLORS[event.source] || '#6b7280',
    extendedProps: {
      source: event.source,
      location: event.location,
      description: event.description,
    },
  }
}

export default function CalendarView({ mode }: CalendarViewProps) {
  const initialView = mode === 'day' ? 'timeGridDay' : 'timeGridWeek'
  const { events } = useEvents()

  const calendarEvents = useMemo(
    () => events.map(toFullCalendarEvent),
    [events]
  )

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
      />
    </div>
  )
}
