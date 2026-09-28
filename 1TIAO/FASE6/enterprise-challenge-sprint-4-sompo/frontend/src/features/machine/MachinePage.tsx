import { useParams } from 'react-router-dom'
import { MachineView } from './MachineView'

function MachinePage() {
  const { tractorId } = useParams()
  return tractorId ? <MachineView tractorId={tractorId} /> : null
}
export { MachinePage }
