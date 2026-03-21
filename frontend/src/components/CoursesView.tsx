import { useState, useEffect } from 'react'
import { useCourses } from '../hooks/useCourses'
import { useTasks } from '../hooks/useTasks'
import { apiFetch } from '../api/client'
import type { Course, Task } from '../types'

export default function CoursesView() {
  const { courses, loading } = useCourses()
  const { tasks } = useTasks(undefined, 'pending')
  const [selectedCourse, setSelectedCourse] = useState<Course | null>(null)

  if (loading) return <div className="text-muted">Loading courses...</div>

  if (courses.length === 0) {
    return (
      <div className="text-center mt-20">
        <p className="text-secondary">No courses found.</p>
        <p className="text-muted text-sm mt-2">Connect Canvas in Settings to import your courses.</p>
      </div>
    )
  }

  const getCourseTasks = (courseName: string): Task[] => {
    return tasks.filter(t => t.course === courseName)
  }

  return (
    <div className="h-full flex flex-col md:flex-row gap-4 md:gap-6">
      {/* Course List — hidden on mobile when a course is selected */}
      <div className={`${selectedCourse ? 'hidden md:block' : ''} w-full md:w-80 flex-shrink-0 space-y-3 overflow-y-auto`}>
        <h2 className="font-display font-bold text-xl text-primary mb-4">Courses</h2>
        {courses.map((course) => {
          const courseTasks = getCourseTasks(course.name)
          const isSelected = selectedCourse?.id === course.id
          return (
            <button
              key={course.id}
              onClick={() => setSelectedCourse(course)}
              className={`w-full text-left p-4 rounded-xl border transition-all ${
                isSelected
                  ? 'bg-accent-light border-accent shadow-card'
                  : 'bg-surface border-border hover:shadow-card shadow-soft'
              }`}
            >
              <div className="flex items-center justify-between">
                <p className={`font-medium text-sm ${isSelected ? 'text-accent' : 'text-primary'}`}>{course.code || course.name}</p>
                {course.current_grade && (
                  <span className="text-xs font-semibold text-accent bg-accent-light px-2 py-0.5 rounded-full">{course.current_grade}</span>
                )}
              </div>
              <p className="text-secondary text-xs mt-0.5 truncate">{course.name}</p>
              <div className="flex items-center gap-3 mt-2 text-xs text-muted">
                <span>{courseTasks.length} pending tasks</span>
                {course.syllabus_url && <span className="text-success">Syllabus found</span>}
              </div>
            </button>
          )
        })}
      </div>

      {/* Course Detail — full width on mobile */}
      <div className={`${!selectedCourse ? 'hidden md:block' : ''} flex-1 overflow-y-auto`}>
        {selectedCourse ? (
          <div>
            {/* Back button on mobile */}
            <button
              onClick={() => setSelectedCourse(null)}
              className="md:hidden text-accent text-sm font-medium mb-3 flex items-center gap-1"
            >
              &larr; Back to courses
            </button>
            <CourseDetail course={selectedCourse} tasks={getCourseTasks(selectedCourse.name)} />
          </div>
        ) : (
          <div className="hidden md:block text-muted text-center mt-20">
            Select a course to view details
          </div>
        )}
      </div>
    </div>
  )
}

function CourseDetail({ course, tasks }: { course: Course; tasks: Task[] }) {
  const [grades, setGrades] = useState<any[]>([])
  const [currentGrade, setCurrentGrade] = useState<string | null>(course.current_grade || null)

  useEffect(() => {
    apiFetch<any>(`/api/courses/${course.id}`).then(data => {
      if (data.grades) setGrades(data.grades)
      if (data.current_grade) setCurrentGrade(data.current_grade)
    }).catch(() => {})
  }, [course.id])

  return (
    <div>
      <h2 className="font-display font-bold text-xl text-primary">{course.code || course.name}</h2>
      <p className="text-secondary text-sm mt-1">{course.name}</p>

      {/* Syllabus Section */}
      <div className="mt-6 p-4 bg-sand rounded-xl">
        <h3 className="font-display font-semibold text-xs text-muted uppercase tracking-wider mb-3">Syllabus</h3>
        {course.syllabus_url ? (
          <div>
            <a
              href={course.syllabus_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:text-accent-hover text-sm underline"
            >
              Open Syllabus
            </a>
            {course.syllabus_text && course.syllabus_text.length > 10 && (
              <div className="mt-3 text-xs text-secondary whitespace-pre-wrap max-h-60 overflow-y-auto">
                {course.syllabus_text}
              </div>
            )}
          </div>
        ) : course.syllabus_text && course.syllabus_text.length > 10 ? (
          <div className="text-xs text-secondary whitespace-pre-wrap max-h-60 overflow-y-auto">
            {course.syllabus_text}
          </div>
        ) : (
          <p className="text-muted text-sm">No syllabus found on Canvas.</p>
        )}
      </div>

      {/* Grades Section */}
      <div className="mt-6 p-4 bg-sand rounded-xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-display font-semibold text-sm text-secondary uppercase tracking-wider">Grades</h3>
          {currentGrade && (
            <span className="text-lg font-display font-bold text-primary">{currentGrade}</span>
          )}
        </div>
        {grades.length > 0 ? (
          <div className="space-y-1.5">
            {grades.map((g: any, i: number) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-0">
                <span className="text-sm text-primary truncate flex-1">{g.assignment_name}</span>
                <span className={`text-sm font-medium ml-4 ${g.score ? 'text-primary' : 'text-muted'}`}>
                  {g.score || '-'}{g.points_possible ? ` / ${g.points_possible}` : ''}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-muted text-sm">No grades available yet.</p>
        )}
      </div>

      {/* Course info */}
      {course.instructor && (
        <div className="mt-4">
          <span className="text-muted text-sm">Instructor: </span>
          <span className="text-primary text-sm">{course.instructor}</span>
        </div>
      )}

      {/* Pending Assignments */}
      <div className="mt-6">
        <h3 className="font-display font-semibold text-xs text-muted uppercase tracking-wider mb-3">
          Pending Assignments ({tasks.length})
        </h3>
        {tasks.length === 0 ? (
          <p className="text-muted text-sm">No pending assignments.</p>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => (
              <div key={task.id} className="p-3 bg-sand rounded-lg">
                <div className="flex items-center justify-between">
                  <p className="text-primary text-sm font-medium">{task.title}</p>
                  {task.current_grade && (
                    <span className="text-xs text-secondary">Grade: {task.current_grade}</span>
                  )}
                </div>
                {task.deadline && (
                  <p className="text-xs text-secondary mt-1">
                    Due: {new Date(task.deadline).toLocaleDateString('en-US', {
                      weekday: 'short', month: 'short', day: 'numeric',
                      hour: 'numeric', minute: '2-digit',
                    })}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {course.updated_at && (
        <p className="text-xs text-muted mt-6">
          Last synced: {new Date(course.updated_at).toLocaleString()}
        </p>
      )}
    </div>
  )
}
