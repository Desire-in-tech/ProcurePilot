import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import Overview from './pages/Overview'
import ProcurementDetail from './pages/ProcurementDetail'
import Procurements from './pages/Procurements'
import Settings from './pages/Settings'
import Suppliers from './pages/Suppliers'
import SupplierCompare from './pages/SupplierCompare'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Overview />} />
          <Route path="/procurements" element={<Procurements />} />
          <Route
            path="/procurements/:id"
            element={<ProcurementDetail />}
          />
          <Route
            path="/procurements/:id/suppliers"
            element={<Suppliers />}
          />
          <Route
            path="/procurements/:id/compare"
            element={<SupplierCompare />}
          />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
