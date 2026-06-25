import { Navigate, Route, Routes } from 'react-router-dom'
import AdminApp from './admin/AdminApp'
import CareApp from './CareApp'

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/admin/*" element={<AdminApp />} />
      <Route path="/*" element={<CareApp />} />
    </Routes>
  )
}
