function Settings() {
  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">CONFIGURATION</p>
          <h1>Settings</h1>
          <p className="page-description">
            Configure your ProcurePilot workspace.
          </p>
        </div>
      </header>

      <div className="empty-state settings-empty">
        <h3>Workspace settings</h3>
        <p>
          Organization preferences, procurement rules and agent configuration
          will live here.
        </p>
      </div>
    </div>
  )
}

export default Settings
