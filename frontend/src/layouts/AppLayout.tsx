import { NavLink, Outlet } from 'react-router-dom'
import { ClipboardList, LayoutDashboard, Settings, Sparkles } from 'lucide-react'

function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">P</div>
          <div>
            <div className="brand-name">ProcurePilot</div>
            <div className="brand-tagline">Procurement, simplified.</div>
          </div>
        </div>

        <nav className="navigation">
          <NavLink
            to="/"
            className={({ isActive }) =>
              `nav-item ${isActive ? 'active' : ''}`
            }
          >
            <LayoutDashboard size={19} />
            <span>Overview</span>
          </NavLink>

          <NavLink
            to="/procurements"
            className={({ isActive }) =>
              `nav-item ${isActive ? 'active' : ''}`
            }
          >
            <ClipboardList size={19} />
            <span>Procurements</span>
          </NavLink>

          <NavLink
            to="/settings"
            className={({ isActive }) =>
              `nav-item ${isActive ? 'active' : ''}`
            }
          >
            <Settings size={19} />
            <span>Settings</span>
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <div className="pilot-card">
            <Sparkles size={18} />
            <div>
              <strong>ProcurePilot</strong>
              <span>Your procurement agent</span>
            </div>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}

export default AppLayout
