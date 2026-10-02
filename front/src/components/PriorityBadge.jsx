import { PRIORITY } from '../mocks/routes'

export default function PriorityBadge({ priority }) {
  const meta = PRIORITY[priority] || PRIORITY.routine
  return <span className={`priority priority-${meta.tone}`}>{meta.label}</span>
}
