import { Routes, Route, Navigate } from 'react-router-dom'
import Navbar from './components/Navbar'
import ProtectedRoute from './components/ProtectedRoute'
import Dashboard from './pages/Dashboard'
import Accounts from './pages/Accounts'
import Transactions from './pages/Transactions'
import Strategies from './pages/Strategies'
import Reports from './pages/Reports'
import Login from './pages/Login'
import Screeners from './pages/Screeners'
import IpoTracker from './pages/IpoTracker'
import Register from './pages/Register'
import ForgotPassword from './pages/ForgotPassword'
import ChangePassword from './pages/ChangePassword'

function App() {
  return (
    <div className="min-h-screen">
      <Navbar />
      <div className="w-full px-4 py-6">
        <Routes>
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/accounts" element={<ProtectedRoute><Accounts /></ProtectedRoute>} />
          <Route path="/transactions" element={<ProtectedRoute><Transactions /></ProtectedRoute>} />
          <Route path="/strategies" element={<ProtectedRoute><Strategies /></ProtectedRoute>} />
          <Route path="/screeners" element={<ProtectedRoute><Screeners /></ProtectedRoute>} />
          <Route path="/ipos" element={<ProtectedRoute><IpoTracker /></ProtectedRoute>} />
          <Route path="/reports" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
          <Route path="/change-password" element={<ProtectedRoute><ChangePassword /></ProtectedRoute>} />
          <Route path="/login" element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/register" element={<Register />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </div>
    </div>
  )
}

export default App
