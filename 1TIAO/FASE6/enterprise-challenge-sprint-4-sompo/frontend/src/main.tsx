import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { RouterProvider } from 'react-router-dom'
import { router } from './app/router'
import { SessionProvider } from './app/AuthSession'

const rootElement = document.getElementById('root')

if (rootElement === null) {
  throw new Error('Elemento raiz do dashboard não foi encontrado.')
}

createRoot(rootElement).render(
  <StrictMode>
    <SessionProvider><RouterProvider router={router} /></SessionProvider>
  </StrictMode>,
)
