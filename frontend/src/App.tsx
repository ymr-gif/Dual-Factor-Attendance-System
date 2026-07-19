import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { getToken } from './api'
import Dashboard from './pages/Dashboard'
import Kiosk from './pages/Kiosk'
import Viewer from './pages/Viewer'
import Roster from './pages/Roster'
import Register from './pages/Register'
import Review from './pages/Review'
import Settings from './pages/Settings'
import Summary from './pages/Summary'
import Sessions from './pages/Sessions'
import Audit from './pages/Audit'
import Reenroll from './pages/Reenroll'
import Lookup from './pages/Lookup'
import Ops from './pages/Ops'
import SetupWizard from './pages/SetupWizard'

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
        {authed && <NavLink to="/summary">Summary</NavLink>}
        {authed && <NavLink to="/sessions">Sessions</NavLink>}
        {authed && <NavLink to="/roster">Roster</NavLink>}
        {authed && <NavLink to="/register">Register</NavLink>}
        {authed && <NavLink to="/review">Review</NavLink>}
        {authed && <NavLink to="/audit">Audit</NavLink>}
        {authed && <NavLink to="/reenroll">Re-enroll</NavLink>}
        {authed && <NavLink to="/lookup">Lookup</NavLink>}
        {authed && <NavLink to="/ops">Ops</NavLink>}
        {authed && <NavLink to="/settings">Settings</NavLink>}
        <span className="spacer" />
        <NavLink to="/setup">Setup</NavLink>
        <NavLink to="/viewer">Viewer</NavLink>
        <NavLink to="/kiosk">Kiosk</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/viewer" element={<Viewer />} />
        <Route path="/kiosk" element={<Kiosk />} />
        <Route path="/summary" element={<Summary />} />
        <Route path="/sessions" element={<Sessions />} />
        <Route path="/roster" element={<Roster />} />
        <Route path="/register" element={<Register />} />
        <Route path="/review" element={<Review />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/reenroll" element={<Reenroll />} />
        <Route path="/lookup" element={<Lookup />} />
        <Route path="/ops" element={<Ops />} />
        <Route path="/setup" element={<SetupWizard />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </BrowserRouter>
  )
}
