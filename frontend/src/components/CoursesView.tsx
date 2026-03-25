import { useState } from 'react'
import { useCourses } from '../hooks/useCourses'
import { useTasks } from '../hooks/useTasks'
import type { Course, Task } from '../types'
import GradeCalculator from './GradeCalculator'

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
  return (
    <div>
      <h2 className="font-display font-bold text-xl text-primary">{course.code || course.name}</h2>
      <p className="text-secondary text-sm mt-1">{course.name}</p>

      {/* Syllabus Section */}
      <SyllabusPanel
        courseId={course.id}
        syllabusUrl={course.syllabus_url}
        syllabusText={course.syllabus_text}
        syllabusFile={course.syllabus_file}
      />

      {/* Grade Calculator */}
      <GradeCalculator courseId={course.id} />

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

function SyllabusPanel({ courseId, syllabusUrl, syllabusText, syllabusFile }: {
  courseId: number
  syllabusUrl: string | null
  syllabusText: string | null
  syllabusFile: string | null
}) {
  const [open, setOpen] = useState(false)

  const hasSyllabus = syllabusFile || syllabusUrl || (syllabusText && syllabusText.length > 10)

  // Use our own server to serve the file — no CORS/X-Frame issues
  const embedUrl = syllabusFile ? `/api/courses/${courseId}/syllabus-file` : null

  // Clean HTML tags from syllabus_text for display
  const cleanText = syllabusText
    ? syllabusText.replace(/<[^>]+>/g, '').trim()
    : null

  return (
    <div className="mt-6 bg-sand rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-4 hover:bg-border/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <h3 className="font-display font-semibold text-sm text-primary">Syllabus</h3>
          {hasSyllabus ? (
            <span className="text-[10px] font-medium text-success bg-success/10 px-1.5 py-0.5 rounded-full">Available</span>
          ) : (
            <span className="text-[10px] font-medium text-muted bg-cream px-1.5 py-0.5 rounded-full">Not found</span>
          )}
        </div>
        <span className={`text-muted transition-transform duration-200 ${open ? 'rotate-180' : ''}`}>
          {'\u25BC'}
        </span>
      </button>

      {open && (
        <div className="border-t border-border/50">
          {!hasSyllabus ? (
            <p className="text-muted text-sm p-4">No syllabus found on Canvas.</p>
          ) : (
            <div>
              {/* Action bar */}
              <div className="flex items-center gap-3 px-4 py-2 bg-cream/50">
                {embedUrl && (
                  <a
                    href={embedUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:text-accent-hover text-xs font-medium flex items-center gap-1"
                  >
                    Open in new tab {'\u2197'}
                  </a>
                )}
                {embedUrl && (
                  <a
                    href={embedUrl}
                    download
                    className="text-secondary hover:text-primary text-xs font-medium flex items-center gap-1"
                  >
                    Download {'\u2193'}
                  </a>
                )}
                {!embedUrl && syllabusUrl && (
                  <a
                    href={syllabusUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:text-accent-hover text-xs font-medium flex items-center gap-1"
                  >
                    Open in new tab {'\u2197'}
                  </a>
                )}
              </div>

              {/* Embedded PDF viewer from our server */}
              {embedUrl ? (
                <object
                  data={embedUrl}
                  type="application/pdf"
                  className="w-full"
                  style={{ height: '70vh', minHeight: '400px' }}
                >
                  <div className="p-6 flex flex-col items-center gap-3">
                    <p className="text-secondary text-sm">PDF viewer not supported in this browser</p>
                    <a
                      href={embedUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-5 py-2 bg-accent hover:bg-accent-hover text-white text-sm font-medium rounded-xl transition-colors"
                    >
                      Open PDF {'\u2197'}
                    </a>
                  </div>
                </object>
              ) : syllabusUrl ? (
                <div className="p-6 flex flex-col items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center text-accent text-xl">
                    {'\u{1F4C4}'}
                  </div>
                  <p className="text-primary text-sm font-medium text-center">Syllabus is hosted externally</p>
                  <a
                    href={syllabusUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-5 py-2 bg-accent hover:bg-accent-hover text-white text-sm font-medium rounded-xl transition-colors"
                  >
                    Open Syllabus {'\u2197'}
                  </a>
                </div>
              ) : cleanText && cleanText.length > 10 ? (
                <div className="p-4 text-sm text-primary leading-relaxed whitespace-pre-wrap max-h-[40vh] overflow-y-auto">
                  {cleanText}
                </div>
              ) : (
                <p className="text-muted text-sm p-4">No syllabus content available.</p>
              )}

              {/* Show text body below embed if there's supplementary text content */}
              {embedUrl && cleanText && cleanText.length > 10 && (
                <div className="p-4 text-sm text-primary leading-relaxed whitespace-pre-wrap max-h-[20vh] overflow-y-auto border-t border-border/50">
                  {cleanText}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
