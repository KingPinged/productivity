import type { ScheduleBlock } from '../types'

const BLOCK_TYPE_LABELS: Record<string, string> = {
  study: 'Study',
  meeting: 'Meeting',
  rest: 'Break',
  personal: 'Personal',
  buffer: 'Buffer',
}

interface BlockDetailProps {
  block: ScheduleBlock
  onClose: () => void
  onComplete: (blockId: number) => void
  onSkip: (blockId: number) => void
}

export default function BlockDetail({ block, onClose, onComplete, onSkip }: BlockDetailProps) {
  return (
    <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white border border-border rounded-2xl p-5 w-96 shadow-elevated"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-display font-bold text-primary">
            {BLOCK_TYPE_LABELS[block.block_type] || block.block_type}
          </h3>
          <button onClick={onClose} className="text-muted hover:text-primary text-lg">
            {'\u2715'}
          </button>
        </div>

        <div className="space-y-3 text-sm">
          <div>
            <span className="text-secondary">Time: </span>
            <span className="text-primary">{block.start_time} &mdash; {block.end_time}</span>
          </div>

          <div>
            <span className="text-secondary">Status: </span>
            <span className={`font-medium ${
              block.status === 'completed' ? 'text-success' :
              block.status === 'skipped' ? 'text-muted' :
              'text-accent'
            }`}>
              {block.status}
            </span>
          </div>

          {block.ai_reason && (
            <div>
              <span className="text-secondary">AI Reasoning: </span>
              <span className="text-primary italic">{block.ai_reason}</span>
            </div>
          )}
        </div>

        {block.status === 'scheduled' && (
          <div className="flex gap-2 mt-5">
            <button
              onClick={() => onComplete(block.id)}
              className="flex-1 py-2 bg-success hover:bg-green-600 rounded-lg text-sm text-white transition-colors"
            >
              Mark Complete
            </button>
            <button
              onClick={() => onSkip(block.id)}
              className="flex-1 py-2 bg-stone-100 hover:bg-stone-200 rounded-lg text-sm text-secondary transition-colors"
            >
              Skip
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
