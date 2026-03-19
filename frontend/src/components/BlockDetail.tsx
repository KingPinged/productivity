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
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-surface-light border border-gray-700 rounded-xl p-5 w-96 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white">
            {BLOCK_TYPE_LABELS[block.block_type] || block.block_type}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-lg">
            {'\u2715'}
          </button>
        </div>

        <div className="space-y-3 text-sm">
          <div>
            <span className="text-gray-400">Time: </span>
            <span className="text-white">{block.start_time} &mdash; {block.end_time}</span>
          </div>

          <div>
            <span className="text-gray-400">Status: </span>
            <span className={`font-medium ${
              block.status === 'completed' ? 'text-green-400' :
              block.status === 'skipped' ? 'text-gray-500' :
              'text-blue-400'
            }`}>
              {block.status}
            </span>
          </div>

          {block.ai_reason && (
            <div>
              <span className="text-gray-400">AI Reasoning: </span>
              <span className="text-gray-300 italic">{block.ai_reason}</span>
            </div>
          )}
        </div>

        {block.status === 'scheduled' && (
          <div className="flex gap-2 mt-5">
            <button
              onClick={() => onComplete(block.id)}
              className="flex-1 py-2 bg-green-600 hover:bg-green-700 rounded text-sm text-white transition-colors"
            >
              Mark Complete
            </button>
            <button
              onClick={() => onSkip(block.id)}
              className="flex-1 py-2 bg-gray-600 hover:bg-gray-700 rounded text-sm text-white transition-colors"
            >
              Skip
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
