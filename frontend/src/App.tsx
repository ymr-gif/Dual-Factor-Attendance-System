import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { getToken } from './api'
import Dashboard from './pages/Dashboard'
import Kiosk from './pages/Kiosk'
import Roster from './pages/Roster'
import Register from './pages/Register'
import Review from './pages/Review'
import Settings from './pages/Settings'

export default function App() {
  const [authed, setAuthed] = useState(() => !!getToken())

  useEffect(() => {
    const h = () => setAuthed(!!getToken())
    window.addEventListener('auth-changed', h as EventListener)
    return () => window.removeEventListener('auth-changed', h as EventListener)
  }, [])

  return (
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
      <nav className="nav">
        <NavLink to="/" end>Dashboard</NavLink>
        {authed && <NavLink to="/roster">Roster</NavLink>}
        {authed && <NavLink to="/register">Register</NavLink>}
        {authed && <NavLink to="/review">Review</NavLink>}
        {authed && <NavLink to="/settings">Settings</NavLink>}
        <span className="spacer" />
        <NavLink to="/kiosk">Kiosk</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/kiosk" element={<Kiosk />} />
        <Route path="/roster" element={<Roster />} />
        <Route path="/register" element={<Register />} />
        <Route path="/review" element={<Review />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </BrowserRouter>
  )
}
