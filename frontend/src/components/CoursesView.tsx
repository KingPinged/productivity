import { useState } from 'react'
import { useCourses } from '../hooks/useCourses'
import { useTasks } from '../hooks/useTasks'
import type { Course, Task } from '../types'

export default function CoursesView() {
  const { courses, loading } = useCourses()
  const { tasks } = useTasks(undefined, 'pending')
  const [selectedCourse, setSelectedCourse] = useState<Course | null>(null)

  if (loading) return <div className="text-gray-400">Loading courses...</div>

  if (courses.length === 0) {
    return (
      <div className="text-center mt-20">
        <p className="text-gray-400">No courses found.</p>
        <p className="text-gray-500 text-sm mt-2">Connect Canvas in Settings to import your courses.</p>
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
        <h2 className="text-xl font-bold mb-4">Courses</h2>
        {courses.map((course) => {
          const courseTasks = getCourseTasks(course.name)
          const isSelected = selectedCourse?.id === course.id
          return (
            <button
              key={course.id}
              onClick={() => setSelectedCourse(course)}
              className={`w-full text-left p-4 rounded-lg border transition-colors ${
                isSelected
                  ? 'bg-accent border-blue-500'
                  : 'bg-gray-800 border-gray-700 hover:border-gray-600'
              }`}
            >
              <p className="text-white font-medium text-sm">{course.code || course.name}</p>
              <p className="text-gray-400 text-xs mt-0.5 truncate">{course.name}</p>
              <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                <span>{courseTasks.length} pending tasks</span>
                {course.syllabus_url && <span className="text-green-400">Syllabus found</span>}
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
          <div className="text-gray-400 text-center mt-20">
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
      <h2 className="text-xl font-bold text-white">{course.code || course.name}</h2>
      <p className="text-gray-400 text-sm mt-1">{course.name}</p>

      {/* Syllabus Section */}
      <div className="mt-6 p-4 bg-surface-light rounded-lg border border-gray-700">
        <h3 className="text-sm font-semibold text-gray-300 uppercase mb-3">Syllabus</h3>
        {course.syllabus_url ? (
          <div>
            <a
              href={course.syllabus_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300 text-sm underline"
            >
              Open Syllabus
            </a>
            {course.syllabus_text && course.syllabus_text.length > 10 && (
              <div className="mt-3 text-xs text-gray-400 whitespace-pre-wrap max-h-60 overflow-y-auto">
                {course.syllabus_text}
              </div>
            )}
          </div>
        ) : course.syllabus_text && course.syllabus_text.length > 10 ? (
          <div className="text-xs text-gray-400 whitespace-pre-wrap max-h-60 overflow-y-auto">
            {course.syllabus_text}
          </div>
        ) : (
          <p className="text-gray-500 text-sm">No syllabus found on Canvas.</p>
        )}
      </div>

      {/* Course info */}
      {course.instructor && (
        <div className="mt-4">
          <span className="text-gray-500 text-sm">Instructor: </span>
          <span className="text-gray-300 text-sm">{course.instructor}</span>
        </div>
      )}

      {/* Pending Assignments */}
      <div className="mt-6">
        <h3 className="text-sm font-semibold text-gray-300 uppercase mb-3">
          Pending Assignments ({tasks.length})
        </h3>
        {tasks.length === 0 ? (
          <p className="text-gray-500 text-sm">No pending assignments.</p>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => (
              <div key={task.id} className="p-3 bg-gray-800 rounded-lg">
                <div className="flex items-center justify-between">
                  <p className="text-white text-sm font-medium">{task.title}</p>
                  {task.current_grade && (
                    <span className="text-xs text-gray-400">Grade: {task.current_grade}</span>
                  )}
                </div>
                {task.deadline && (
                  <p className="text-xs text-gray-400 mt-1">
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
        <p className="text-xs text-gray-600 mt-6">
          Last synced: {new Date(course.updated_at).toLocaleString()}
        </p>
      )}
    </div>
  )
}
