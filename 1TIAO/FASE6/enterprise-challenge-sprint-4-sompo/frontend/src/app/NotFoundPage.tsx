import { Link } from 'react-router-dom'

function NotFoundPage() {
  return <main className="page"><h1>Página não encontrada</h1><p><Link to="/">Voltar para a máquina</Link></p></main>
}

export { NotFoundPage }
