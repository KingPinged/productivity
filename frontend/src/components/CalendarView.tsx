import { useState, useEffect, useMemo, useCallback } from 'react'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import { useEvents } from '../hooks/useEvents'
import { useSchedule } from '../hooks/useSchedule'
import { apiFetch } from '../api/client'
import BlockDetail from './BlockDetail'
import EventModal from './EventModal'
import type { CalendarEvent, ScheduleBlock } from '../types'

interface CalendarViewProps {
  mode: 'day' | 'week'
}

const SOURCE_COLORS: Record<string, string> = {
  gcal: '#34D399',
  gmail: '#818CF8',
  canvas: '#FBBF24',
  manual: '#F472B6',
}

const BLOCK_COLORS: Record<string, string> = {
  study: '#818CF8',
  meeting: '#34D399',
  rest: '#FBBF24',
  personal: '#F472B6',
  buffer: '#A8A29E',
}

function toFullCalendarEvent(event: CalendarEvent) {
  return {
    id: `event-${event.id}`,
    title: event.title,
    start: event.start_time,
    end: event.end_time || undefined,
    allDay: event.all_day,
    backgroundColor: SOURCE_COLORS[event.source] || '#A8A29E',
    borderColor: SOURCE_COLORS[event.source] || '#A8A29E',
    extendedProps: { type: 'event', source: event.source },
  }
}

function blockToFullCalendar(block: ScheduleBlock) {
  const date = block.date
  const label = block.ai_reason || block.block_type.charAt(0).toUpperCase() + block.block_type.slice(1)
  return {
    id: `block-${block.id}`,
    title: label,
    start: `${date}T${block.start_time}:00`,
    end: `${date}T${block.end_time}:00`,
    backgroundColor: block.status === 'completed' ? '#F5F0EB' : (BLOCK_COLORS[block.block_type] || '#A8A29E'),
    borderColor: block.status === 'completed' ? '#E7E5E4' : (BLOCK_COLORS[block.block_type] || '#A8A29E'),
    textColor: block.status === 'completed' ? '#A8A29E' : '#ffffff',
    extendedProps: { type: 'block', block },
    editable: true,
  }
}

function useWeekSchedule() {
  const [blocks, setBlocks] = useState<ScheduleBlock[]>([])

  const load = useCallback(async () => {
    try {
      const today = new Date()
      const allBlocks: ScheduleBlock[] = []
      for (let i = 0; i < 7; i++) {
        const d = new Date(today)
        d.setDate(d.getDate() + i)
        const dateStr = d.toISOString().split('T')[0]
        const { apiFetch } = await import('../api/client')
        const data = await apiFetch<{ blocks: ScheduleBlock[] }>(`/api/schedule/${dateStr}`)
        allBlocks.push(...data.blocks)
      }
      setBlocks(allBlocks)
    } catch (err) {
      console.error('Failed to load week schedule:', err)
    }
  }, [])

  useEffect(() => { load() }, [load])
  return { blocks, reload: load }
}

export default function CalendarView({ mode }: CalendarViewProps) {
  const initialView = mode === 'day' ? 'timeGridDay' : 'timeGridWeek'
  const today = new Date().toISOString().split('T')[0]
  const { events, reload: reloadEvents } = useEvents()
  const { schedule, updateBlock, triggerReplan } = useSchedule(today)
  const weekSchedule = useWeekSchedule()
  const [selectedBlock, setSelectedBlock] = useState<ScheduleBlock | null>(null)
  const [eventModal, setEventModal] = useState<{
    mode: 'create' | 'edit'
    event?: CalendarEvent
    defaultStart?: string
    defaultEnd?: string
  } | null>(null)

  const calendarEvents = useMemo(() => {
    const eventItems = events.map(toFullCalendarEvent)
    const scheduleBlocks = mode === 'week'
      ? weekSchedule.blocks
      : (schedule?.blocks || [])
    const blockItems = scheduleBlocks.map(blockToFullCalendar)
    return [...eventItems, ...blockItems]
  }, [events, schedule, weekSchedule.blocks, mode])

  // Click/drag empty slot to create a new event
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleSelect = useCallback((info: any) => {
    setEventModal({
      mode: 'create',
      defaultStart: info.startStr,
      defaultEnd: info.endStr,
    })
  }, [])

  // Click existing event — events open EventModal, blocks open BlockDetail
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleEventClick = useCallback((info: any) => {
    const props = info.event.extendedProps
    if (props.type === 'block' && props.block) {
      setSelectedBlock(props.block as ScheduleBlock)
    } else if (props.type === 'event') {
      const eventId = parseInt(info.event.id.replace('event-', ''))
      const originalEvent = events.find((e: CalendarEvent) => e.id === eventId)
      if (originalEvent) {
        setEventModal({ mode: 'edit', event: originalEvent })
      }
    }
  }, [events])

  // Drag-drop to move events or blocks
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleEventDrop = useCallback(async (info: any) => {
    const props = info.event.extendedProps
    if (props.type === 'event') {
      const eventId = parseInt(info.event.id.replace('event-', ''))
      try {
        await apiFetch(`/api/events/${eventId}`, {
          method: 'PATCH',
          body: JSON.stringify({
            start_time: info.event.startStr,
            end_time: info.event.endStr,
          }),
        })
        reloadEvents()
      } catch {
        info.revert()
      }
    } else if (props.type === 'block' && props.block) {
      const block = props.block as ScheduleBlock
      try {
        const newStart = info.event.start?.toTimeString().slice(0, 5) || block.start_time
        const newEnd = info.event.end?.toTimeString().slice(0, 5) || block.end_time
        await updateBlock(block.id, { start_time: newStart, end_time: newEnd })
        await triggerReplan()
      } catch {
        info.revert()
      }
    }
  }, [updateBlock, triggerReplan, reloadEvents])

  // Drag bottom edge to resize (change end time)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleEventResize = useCallback(async (info: any) => {
    const props = info.event.extendedProps
    if (props.type === 'event') {
      const eventId = parseInt(info.event.id.replace('event-', ''))
      try {
        await apiFetch(`/api/events/${eventId}`, {
          method: 'PATCH',
          body: JSON.stringify({ end_time: info.event.endStr }),
        })
        reloadEvents()
      } catch {
        info.revert()
      }
    } else if (props.type === 'block' && props.block) {
      const block = props.block as ScheduleBlock
      try {
        const newEnd = info.event.end?.toTimeString().slice(0, 5) || block.end_time
        await updateBlock(block.id, { end_time: newEnd })
      } catch {
        info.revert()
      }
    }
  }, [updateBlock, reloadEvents])

  const handleComplete = useCallback(async (blockId: number) => {
    await updateBlock(blockId, { status: 'completed' })
    setSelectedBlock(null)
  }, [updateBlock])

  const handleSkip = useCallback(async (blockId: number) => {
    await updateBlock(blockId, { status: 'skipped' })
    setSelectedBlock(null)
  }, [updateBlock])

  const handleEventSaved = useCallback(() => {
    reloadEvents()
  }, [reloadEvents])

  return (
    <div className="h-full">
      <FullCalendar
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView={initialView}
        headerToolbar={
          window.innerWidth < 768
            ? { left: 'prev,next', center: 'title', right: 'today' }
            : { left: 'prev,next today', center: 'title', right: 'timeGridDay,timeGridWeek' }
        }
        editable={true}
        selectable={true}
        selectMirror={true}
        eventResizableFromStart={false}
        nowIndicator={true}
        slotMinTime="06:00:00"
        slotMaxTime="24:00:00"
        height="100%"
        events={calendarEvents}
        select={handleSelect}
        eventClick={handleEventClick}
        eventDrop={handleEventDrop}
        eventResize={handleEventResize}
        longPressDelay={200}
        selectLongPressDelay={300}
        slotLabelFormat={{
          hour: 'numeric',
          minute: '2-digit',
          meridiem: 'short',
        }}
        eventTimeFormat={{
          hour: 'numeric',
          minute: '2-digit',
          meridiem: 'short',
        }}
      />

      {selectedBlock && (
        <BlockDetail
          block={selectedBlock}
          onClose={() => setSelectedBlock(null)}
          onComplete={handleComplete}
          onSkip={handleSkip}
        />
      )}

      {eventModal && (
        <EventModal
          mode={eventModal.mode}
          event={eventModal.event}
          defaultStart={eventModal.defaultStart}
          defaultEnd={eventModal.defaultEnd}
          onClose={() => setEventModal(null)}
          onSaved={handleEventSaved}
        />
      )}
    </div>
  )
}
