import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'

interface CalendarViewProps {
  mode: 'day' | 'week'
}

export default function CalendarView({ mode }: CalendarViewProps) {
  const initialView = mode === 'day' ? 'timeGridDay' : 'timeGridWeek'

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
        events={[]}
      />
    </div>
  )
}
