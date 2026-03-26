import { useState, useEffect, useCallback, useMemo } from 'react'
import { apiFetch } from '../api/client'
import type { GradeCalculatorData, GradeCategory } from '../types'

interface Override {
  gradeId: number | null
  category: string
  name: string
  score: number
  pointsPossible: number
}

export function useGradeCalculator(courseId: number | null) {
  const [data, setData] = useState<GradeCalculatorData | null>(null)
  const [loading, setLoading] = useState(false)
  const [overrides, setOverrides] = useState<Map<string, Override>>(new Map())

  const load = useCallback(async () => {
    if (!courseId) return
    setLoading(true)
    try {
      const result = await apiFetch<GradeCalculatorData>(`/api/courses/${courseId}/grade-calculator`)
      setData(result)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [courseId])

  useEffect(() => {
    load()
    setOverrides(new Map())
  }, [load])

  const setOverride = useCallback((key: string, override: Override) => {
    setOverrides(prev => {
      const next = new Map(prev)
      next.set(key, override)
      return next
    })
  }, [])

  const removeOverride = useCallback((key: string) => {
    setOverrides(prev => {
      const next = new Map(prev)
      next.delete(key)
      return next
    })
  }, [])

  const resetOverrides = useCallback(() => {
    setOverrides(new Map())
  }, [])

  // Client-side grade computation with overrides applied
  const computed = useMemo(() => {
    if (!data) return null
    return computeWithOverrides(data, overrides)
  }, [data, overrides])

  const saveCategories = useCallback(async (categories: Array<{ name: string; weight: number }>) => {
    if (!courseId) return
    await apiFetch(`/api/courses/${courseId}/grade-categories`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ categories }),
    })
    await load()
  }, [courseId, load])

  const saveScale = useCallback(async (scale: Array<{ letter: string; min_percent: number; max_percent: number | null }>) => {
    if (!courseId) return
    await apiFetch(`/api/courses/${courseId}/grade-scale`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scale }),
    })
    await load()
  }, [courseId, load])

  const reparseSyllabus = useCallback(async () => {
    if (!courseId) return
    await apiFetch(`/api/courses/${courseId}/reparse-syllabus`, { method: 'POST' })
    await load()
  }, [courseId, load])

  const moveAssignment = useCallback(async (gradeId: number, category: string | null) => {
    await apiFetch(`/api/grades/${gradeId}/category`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category }),
    })
    await load()
  }, [load])

  const deleteAssignment = useCallback(async (gradeId: number) => {
    await apiFetch(`/api/grades/${gradeId}`, { method: 'DELETE' })
    await load()
  }, [load])

  return {
    data: computed,
    rawData: data,
    loading,
    overrides,
    setOverride,
    removeOverride,
    resetOverrides,
    saveCategories,
    saveScale,
    reparseSyllabus,
    moveAssignment,
    deleteAssignment,
    reload: load,
  }
}

function computeWithOverrides(
  data: GradeCalculatorData,
  overrides: Map<string, Override>,
): GradeCalculatorData {
  if (overrides.size === 0) return data

  const categories: GradeCategory[] = data.categories.map(cat => {
    let earned = 0
    let possible = 0
    const assignments = cat.assignments.map(a => {
      const key = a.id != null ? `existing-${a.id}` : `hyp-${a.name}`
      const ov = overrides.get(key)
      const score = ov ? String(ov.score) : a.score
      const pp = ov ? String(ov.pointsPossible) : a.points_possible
      const scoreNum = score != null ? parseFloat(score) : null
      const ppNum = pp != null ? parseFloat(pp) : null

      if (scoreNum != null && !isNaN(scoreNum) && ppNum != null && !isNaN(ppNum) && ppNum > 0) {
        earned += scoreNum
        possible += ppNum
      }

      return { ...a, score, points_possible: pp }
    })

    // Add new hypothetical overrides for this category
    for (const [key, ov] of overrides) {
      if (key.startsWith('new-') && ov.category === cat.name) {
        assignments.push({
          id: null,
          name: ov.name || 'Hypothetical',
          score: String(ov.score),
          points_possible: String(ov.pointsPossible),
          category: cat.name,
          hypothetical: true,
        })
        earned += ov.score
        possible += ov.pointsPossible
      }
    }

    return {
      ...cat,
      earned,
      possible,
      score: possible > 0 ? Math.round(earned / possible * 10000) / 100 : null,
      assignments,
    }
  })

  // Weighted grade
  let activeWeightSum = 0
  let weightedSum = 0
  for (const cat of categories) {
    if (cat.weight > 0 && cat.score != null) {
      weightedSum += cat.score * cat.weight / 100
      activeWeightSum += cat.weight
    }
  }

  let weightedGrade: number | null = null
  if (activeWeightSum > 0) {
    weightedGrade = Math.round(weightedSum / activeWeightSum * 10000) / 100
  } else {
    const totalEarned = categories.reduce((s, c) => s + c.earned, 0)
    const totalPossible = categories.reduce((s, c) => s + c.possible, 0)
    weightedGrade = totalPossible > 0 ? Math.round(totalEarned / totalPossible * 10000) / 100 : null
  }

  // Letter grade
  let letterGrade: string | null = null
  if (weightedGrade != null && data.gradeScale.length > 0) {
    const sorted = [...data.gradeScale].sort((a, b) => b.minPercent - a.minPercent)
    for (const entry of sorted) {
      if (weightedGrade >= entry.minPercent) {
        letterGrade = entry.letter
        break
      }
    }
  }

  return { categories, weightedGrade, letterGrade, gradeScale: data.gradeScale }
}
