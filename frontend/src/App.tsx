import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Kiosk from './pages/Kiosk'

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/kiosk" element={<Kiosk />} />
      </Routes>
    </BrowserRouter>
  )
}
