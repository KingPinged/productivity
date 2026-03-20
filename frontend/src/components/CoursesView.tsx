import { useState } from 'react'
import { useCourses } from '../hooks/useCourses'
import { useTasks } from '../hooks/useTasks'
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
    <div className="h-full flex gap-6">
      {/* Course List */}
      <div className="w-80 flex-shrink-0 space-y-3 overflow-y-auto">
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
              <p className={`font-medium text-sm ${isSelected ? 'text-accent' : 'text-primary'}`}>{course.code || course.name}</p>
              <p className="text-secondary text-xs mt-0.5 truncate">{course.name}</p>
              <div className="flex items-center gap-3 mt-2 text-xs text-muted">
                <span>{courseTasks.length} pending tasks</span>
                {course.syllabus_url && <span className="text-success">Syllabus found</span>}
              </div>
            </button>
          )
        })}
      </div>

      {/* Course Detail */}
      <div className="flex-1 overflow-y-auto">
        {selectedCourse ? (
          <CourseDetail course={selectedCourse} tasks={getCourseTasks(selectedCourse.name)} />
        ) : (
          <div className="text-muted text-center mt-20">
            Select a course to view details
          </div>
        )}
      </div>
    </div>
  )
}

function CourseDetail({ course, tasks }: { course: Course; tasks: Task[] }) {
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
