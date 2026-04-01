import { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { useGradeCalculator } from '../hooks/useGradeCalculator'
import type { GradeCategory, GradeAssignment } from '../types'

export default function GradeCalculator({ courseId }: { courseId: number }) {
  const {
    data, loading, overrides,
    setOverride, removeOverride, resetOverrides,
    saveCategories, saveScale, reparseSyllabus,
    moveAssignment, deleteAssignment,
  } = useGradeCalculator(courseId)
  const [editingWeights, setEditingWeights] = useState(false)
  const hasOverrides = overrides.size > 0

  if (loading) return <div className="text-muted text-sm">Loading grades...</div>
  if (!data) return <div className="text-muted text-sm">No grade data available.</div>

  const hasCategories = data.categories.some(c => c.weight > 0)

  return (
    <div className="mt-6">
      {/* Overall Grade Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="font-display font-semibold text-sm text-secondary uppercase tracking-wider">Grade Calculator</h3>
          <button
            onClick={() => setEditingWeights(!editingWeights)}
            className="text-muted hover:text-secondary text-xs"
            title="Edit weights & scale"
          >
            {'\u2699'}
          </button>
          {hasOverrides && (
            <button
              onClick={resetOverrides}
              className="text-xs text-accent hover:text-accent-hover font-medium"
            >
              Reset what-if
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {data.letterGrade && (
            <span className="text-sm font-semibold text-white bg-accent px-2.5 py-0.5 rounded-full">
              {data.letterGrade}
            </span>
          )}
          {data.weightedGrade != null && (
            <span className={`text-2xl font-display font-bold ${hasOverrides ? 'text-amber-700' : 'text-primary'}`}>
              {data.weightedGrade}%
            </span>
          )}
        </div>
      </div>

      {/* Weights Editor */}
      {editingWeights && (
        <WeightsEditor
          categories={data.categories}
          gradeScale={data.gradeScale}
          onSaveCategories={saveCategories}
          onSaveScale={saveScale}
          onReparse={reparseSyllabus}
          onClose={() => setEditingWeights(false)}
        />
      )}

      {/* No categories hint */}
      {!hasCategories && (
        <div className="p-3 bg-cream rounded-lg mb-4 text-sm text-secondary">
          No category weights found. Click the gear icon to add them manually or re-parse the syllabus.
        </div>
      )}

      {/* Category Sections */}
      {data.categories.map(cat => (
        <CategorySection
          key={cat.name}
          category={cat}
          allCategoryNames={data.categories.map(c => c.name)}
          overrides={overrides}
          onSetOverride={setOverride}
          onRemoveOverride={removeOverride}
          onMoveAssignment={moveAssignment}
          onDeleteAssignment={deleteAssignment}
        />
      ))}
    </div>
  )
}

function CategorySection({
  category, allCategoryNames, overrides, onSetOverride, onRemoveOverride, onMoveAssignment, onDeleteAssignment,
}: {
  category: GradeCategory
  allCategoryNames: string[]
  overrides: Map<string, any>
  onSetOverride: (key: string, ov: any) => void
  onRemoveOverride: (key: string) => void
  onMoveAssignment: (gradeId: number, category: string | null) => Promise<void>
  onDeleteAssignment: (gradeId: number) => Promise<void>
}) {
  const [expanded, setExpanded] = useState(true)
  const [addingNew, setAddingNew] = useState(false)
  const hasOverride = category.assignments.some(a => {
    const key = a.id != null ? `existing-${a.id}` : `hyp-${a.name}`
    return overrides.has(key)
  })

  return (
    <div className="mb-3 bg-sand rounded-xl">
      {/* Category Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-border/30 transition-colors rounded-xl"
      >
        <div className="flex items-center gap-2">
          <span className={`text-muted text-xs transition-transform ${expanded ? 'rotate-90' : ''}`}>{'\u25B6'}</span>
          <span className="font-medium text-sm text-primary">{category.name}</span>
          {category.weight > 0 && (
            <span className="text-[10px] font-medium text-accent bg-accent-light px-1.5 py-0.5 rounded-full">
              {category.weight}%
            </span>
          )}
          <span className="text-[10px] text-muted">{category.assignments.length}</span>
        </div>
        <span className={`text-sm font-medium ${hasOverride ? 'text-amber-700' : 'text-primary'}`}>
          {category.score != null ? `${category.score}%` : '-'}
        </span>
      </button>

      {/* Assignments */}
      {expanded && (
        <div className="border-t border-border/50 px-3 pb-2">
          {category.assignments.map((a, i) => (
            <AssignmentRow
              key={a.id ?? `hyp-${i}`}
              assignment={a}
              allCategoryNames={allCategoryNames}
              overrides={overrides}
              onSetOverride={onSetOverride}
              onRemoveOverride={onRemoveOverride}
              onMove={onMoveAssignment}
              onDelete={onDeleteAssignment}
            />
          ))}
          {/* Add hypothetical */}
          {addingNew ? (
            <NewAssignmentRow
              category={category.name}
              onAdd={(ov) => {
                const key = `new-${Date.now()}`
                onSetOverride(key, ov)
                setAddingNew(false)
              }}
              onCancel={() => setAddingNew(false)}
            />
          ) : (
            <button
              onClick={() => setAddingNew(true)}
              className="text-xs text-accent hover:text-accent-hover font-medium py-1.5"
            >
              + Add assignment
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function AssignmentRow({
  assignment, allCategoryNames, overrides, onSetOverride, onRemoveOverride, onMove, onDelete,
}: {
  assignment: GradeAssignment
  allCategoryNames: string[]
  overrides: Map<string, any>
  onSetOverride: (key: string, ov: any) => void
  onRemoveOverride: (key: string) => void
  onMove: (gradeId: number, category: string | null) => Promise<void>
  onDelete: (gradeId: number) => Promise<void>
}) {
  const key = assignment.id != null ? `existing-${assignment.id}` : `hyp-${assignment.name}`
  const hasOverride = overrides.has(key)
  const [editing, setEditing] = useState(false)
  const [showMenu, setShowMenu] = useState(false)
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0 })
  const submitted = useRef(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editing])

  // Close menu on outside click
  useEffect(() => {
    if (!showMenu) return
    const handler = () => setShowMenu(false)
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showMenu])

  const scoreDisplay = assignment.score ?? '-'
  const ppDisplay = assignment.points_possible ?? '?'

  const handleSubmit = useCallback((value: string) => {
    if (submitted.current) return
    submitted.current = true
    const num = parseFloat(value)
    if (!isNaN(num)) {
      onSetOverride(key, {
        gradeId: assignment.id,
        category: assignment.category,
        name: assignment.name,
        score: num,
        pointsPossible: parseFloat(assignment.points_possible || '100'),
      })
    }
    setEditing(false)
  }, [key, assignment, onSetOverride])

  const startEditing = () => {
    submitted.current = false
    setEditing(true)
  }

  const otherCategories = allCategoryNames.filter(c => c !== assignment.category)

  const openMenu = (e: React.MouseEvent) => {
    const rect = (e.target as HTMLElement).getBoundingClientRect()
    setMenuPos({ top: rect.bottom + 2, left: rect.left })
    setShowMenu(true)
  }

  return (
    <div className={`flex items-center justify-between py-1.5 border-b border-border/30 last:border-0 ${
      assignment.hypothetical ? 'bg-accent-light/30' : ''
    } ${hasOverride ? 'bg-amber-50' : ''}`}>
      <div className="flex items-center gap-1 flex-1 min-w-0">
        {/* Context menu trigger */}
        {assignment.id != null && (
          <>
            <button
              ref={btnRef}
              onClick={openMenu}
              className="text-muted hover:text-secondary text-xs px-0.5 shrink-0"
              title="Move or delete"
            >{'\u22EE'}</button>
            {showMenu && createPortal(
              <div
                className="fixed z-50 bg-white border border-border rounded-lg shadow-lg py-1 min-w-[10rem]"
                style={{ top: menuPos.top, left: menuPos.left }}
                onMouseDown={e => e.stopPropagation()}
              >
                {otherCategories.map(cat => (
                  <button
                    key={cat}
                    onClick={async () => { setShowMenu(false); await onMove(assignment.id!, cat) }}
                    className="block w-full text-left text-xs px-3 py-1.5 hover:bg-cream text-primary"
                  >
                    Move to {cat}
                  </button>
                ))}
                {otherCategories.length > 0 && <hr className="my-1 border-border/50" />}
                <button
                  onClick={async () => { setShowMenu(false); await onDelete(assignment.id!) }}
                  className="block w-full text-left text-xs px-3 py-1.5 hover:bg-red-50 text-red-600"
                >
                  Delete
                </button>
              </div>,
              document.body
            )}
          </>
        )}
        <span className="text-sm text-primary truncate">{assignment.name}</span>
      </div>
      <div className="flex items-center gap-1 ml-2">
        {editing ? (
          <input
            ref={inputRef}
            type="number"
            step="any"
            defaultValue={assignment.score ?? ''}
            className="w-16 text-sm text-right border border-accent rounded px-1 py-0.5"
            onBlur={(e) => handleSubmit(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                handleSubmit((e.target as HTMLInputElement).value)
              }
              if (e.key === 'Escape') { submitted.current = true; setEditing(false) }
            }}
          />
        ) : (
          <button
            onClick={startEditing}
            className={`text-sm font-medium text-right min-w-[3rem] ${
              assignment.score ? 'text-primary' : 'text-muted border-b border-dashed border-muted'
            } ${hasOverride ? 'text-amber-700 font-semibold' : ''} hover:text-accent cursor-pointer`}
          >
            {scoreDisplay}
          </button>
        )}
        <span className="text-sm text-muted">/ {ppDisplay}</span>
        {hasOverride && (
          <button
            onClick={() => onRemoveOverride(key)}
            className="text-xs text-muted hover:text-red-500 ml-1"
            title="Remove override"
          >
            {'\u2715'}
          </button>
        )}
      </div>
    </div>
  )
}

function NewAssignmentRow({
  category, onAdd, onCancel,
}: {
  category: string
  onAdd: (ov: any) => void
  onCancel: () => void
}) {
  const [score, setScore] = useState('')
  const [total, setTotal] = useState('100')
  const scoreRef = useRef<HTMLInputElement>(null)

  useEffect(() => { scoreRef.current?.focus() }, [])

  const handleAdd = () => {
    const s = parseFloat(score)
    const t = parseFloat(total)
    if (!isNaN(s) && !isNaN(t) && t > 0) {
      onAdd({
        gradeId: null,
        category,
        name: `What-if ${category}`,
        score: s,
        pointsPossible: t,
      })
    }
  }

  return (
    <div className="flex items-center gap-2 py-1.5">
      <input
        ref={scoreRef}
        type="number"
        placeholder="Score"
        value={score}
        onChange={e => setScore(e.target.value)}
        className="w-16 text-sm border border-border rounded px-1.5 py-0.5"
        onKeyDown={e => { if (e.key === 'Enter') handleAdd(); if (e.key === 'Escape') onCancel() }}
      />
      <span className="text-sm text-muted">/</span>
      <input
        type="number"
        placeholder="Total"
        value={total}
        onChange={e => setTotal(e.target.value)}
        className="w-16 text-sm border border-border rounded px-1.5 py-0.5"
        onKeyDown={e => { if (e.key === 'Enter') handleAdd(); if (e.key === 'Escape') onCancel() }}
      />
      <button onClick={handleAdd} className="text-xs text-accent font-medium">Add</button>
      <button onClick={onCancel} className="text-xs text-muted">Cancel</button>
    </div>
  )
}

function WeightsEditor({
  categories, gradeScale, onSaveCategories, onSaveScale, onReparse, onClose,
}: {
  categories: GradeCategory[]
  gradeScale: Array<{ letter: string; minPercent: number; maxPercent: number | null }>
  onSaveCategories: (cats: Array<{ name: string; weight: number }>) => Promise<void>
  onSaveScale: (scale: Array<{ letter: string; min_percent: number; max_percent: number | null }>) => Promise<void>
  onReparse: () => Promise<void>
  onClose: () => void
}) {
  const [cats, setCats] = useState(
    categories.map(c => ({ name: c.name, weight: c.weight }))
  )
  const [scale, setScale] = useState(
    gradeScale.map(s => ({ letter: s.letter, min_percent: s.minPercent, max_percent: s.maxPercent }))
  )
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSaveCategories(cats)
      await onSaveScale(scale)
      onClose()
    } catch {
      // save failed, stay open so user can retry
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mb-4 p-4 bg-cream rounded-xl border border-border">
      <div className="flex items-center justify-between mb-3">
        <h4 className="font-display font-semibold text-sm text-primary">Category Weights</h4>
        <button onClick={onReparse} className="text-xs text-accent hover:text-accent-hover">
          Re-parse syllabus
        </button>
      </div>

      {/* Category weights */}
      <div className="space-y-1.5 mb-4">
        {cats.map((cat, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              type="text"
              value={cat.name}
              onChange={e => {
                const next = [...cats]
                next[i] = { ...next[i], name: e.target.value }
                setCats(next)
              }}
              className="flex-1 text-sm border border-border rounded px-2 py-1"
            />
            <input
              type="number"
              value={cat.weight}
              onChange={e => {
                const next = [...cats]
                next[i] = { ...next[i], weight: parseFloat(e.target.value) || 0 }
                setCats(next)
              }}
              className="w-16 text-sm text-right border border-border rounded px-2 py-1"
            />
            <span className="text-sm text-muted">%</span>
            <button
              onClick={() => setCats(cats.filter((_, j) => j !== i))}
              className="text-xs text-muted hover:text-red-500"
            >{'\u2715'}</button>
          </div>
        ))}
        <button
          onClick={() => setCats([...cats, { name: '', weight: 0 }])}
          className="text-xs text-accent hover:text-accent-hover font-medium"
        >
          + Add category
        </button>
        <div className="text-xs text-muted mt-1">
          Total: {cats.reduce((s, c) => s + c.weight, 0)}%
        </div>
      </div>

      {/* Grade scale */}
      <h4 className="font-display font-semibold text-sm text-primary mb-2">Grade Scale</h4>
      <div className="space-y-1.5 mb-4">
        {scale.map((s, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              type="text"
              value={s.letter}
              onChange={e => {
                const next = [...scale]
                next[i] = { ...next[i], letter: e.target.value }
                setScale(next)
              }}
              className="w-12 text-sm text-center border border-border rounded px-1 py-1"
            />
            <input
              type="number"
              value={s.min_percent}
              onChange={e => {
                const next = [...scale]
                next[i] = { ...next[i], min_percent: parseFloat(e.target.value) || 0 }
                setScale(next)
              }}
              className="w-16 text-sm text-right border border-border rounded px-2 py-1"
            />
            <span className="text-xs text-muted">-</span>
            <input
              type="number"
              value={s.max_percent ?? 100}
              onChange={e => {
                const next = [...scale]
                next[i] = { ...next[i], max_percent: parseFloat(e.target.value) || null }
                setScale(next)
              }}
              className="w-16 text-sm text-right border border-border rounded px-2 py-1"
            />
            <span className="text-xs text-muted">%</span>
            <button
              onClick={() => setScale(scale.filter((_, j) => j !== i))}
              className="text-xs text-muted hover:text-red-500"
            >{'\u2715'}</button>
          </div>
        ))}
        <button
          onClick={() => setScale([...scale, { letter: '', min_percent: 0, max_percent: null }])}
          className="text-xs text-accent hover:text-accent-hover font-medium"
        >
          + Add grade threshold
        </button>
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-1.5 bg-accent hover:bg-accent-hover text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save'}
        </button>
        <button
          onClick={onClose}
          className="px-4 py-1.5 text-sm text-secondary hover:text-primary"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
