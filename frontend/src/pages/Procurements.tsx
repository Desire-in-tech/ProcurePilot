import { useEffect, useState } from 'react'
import {
  ArrowRight,
  ClipboardList,
  Plus,
  Search,
} from 'lucide-react'
import {
  Link,
  useNavigate,
} from 'react-router-dom'
import {
  createProcurement,
  getProcurements,
} from '../lib/procurement'
import type { ProcurementRequest } from '../types/procurement'

function Procurements() {
  const navigate = useNavigate()

  const [request, setRequest] = useState('')
  const [procurements, setProcurements] = useState<ProcurementRequest[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const [search, setSearch] = useState('')

  useEffect(() => {
    setProcurements(getProcurements())
  }, [])

  function handleCreateProcurement() {
    const trimmedRequest = request.trim()

    if (!trimmedRequest || isCreating) {
      return
    }

    setIsCreating(true)

    const procurement = createProcurement(trimmedRequest)

    setProcurements((current) => [
      procurement,
      ...current,
    ])

    setRequest('')
    setIsCreating(false)

    navigate(`/procurements/${procurement.id}`)
  }

  const filteredProcurements = procurements.filter((procurement) =>
    `${procurement.title} ${procurement.originalRequest}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  )

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">PROCUREMENT WORKSPACE</p>

          <h1>Procurements</h1>

          <p className="page-description">
            Turn what your organization needs into a structured supplier
            search.
          </p>
        </div>

        <button
          className="primary-button"
          onClick={() =>
            document
              .getElementById('procurement-request')
              ?.focus()
          }
        >
          <Plus size={18} />
          New procurement
        </button>
      </header>

      <section className="request-section">
        <div className="section-heading">
          <div>
            <h2>What do you need?</h2>

            <p>
              Describe the product or service you're looking to source.
            </p>
          </div>
        </div>

        <div className="request-card">
          <label htmlFor="procurement-request">
            Procurement request
          </label>

          <textarea
            id="procurement-request"
            value={request}
            onChange={(event) => setRequest(event.target.value)}
            placeholder="Example: We need 25 laptops for our engineering team. They should have at least 16GB RAM, 512GB SSD and come with a 3-year warranty."
            rows={5}
          />

          <div className="request-footer">
            <span>
              ProcurePilot will structure your requirements before
              searching.
            </span>

            <button
              className="primary-button"
              onClick={handleCreateProcurement}
              disabled={!request.trim() || isCreating}
            >
              {isCreating ? 'Creating...' : 'Start procurement'}
              <ArrowRight size={18} />
            </button>
          </div>
        </div>
      </section>

      <section className="recent-section">
        <div className="section-heading">
          <div>
            <h2>Recent procurements</h2>

            <p>
              Your procurement requests and their current status.
            </p>
          </div>

          {procurements.length > 0 && (
            <div className="search-box">
              <Search size={17} />

              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search procurements"
              />
            </div>
          )}
        </div>

        {filteredProcurements.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">
              <ClipboardList size={24} />
            </div>

            <h3>
              {procurements.length === 0
                ? 'No procurements yet'
                : 'No matching procurements'}
            </h3>

            <p>
              {procurements.length === 0
                ? 'Start your first procurement request and ProcurePilot will guide you through the process.'
                : 'Try a different search term.'}
            </p>
          </div>
        ) : (
          <div className="procurement-list">
            {filteredProcurements.map((procurement) => (
              <Link
                key={procurement.id}
                to={`/procurements/${procurement.id}`}
                className="procurement-item"
              >
                <div>
                  <h3>{procurement.title}</h3>

                  <p>{procurement.originalRequest}</p>
                </div>

                <div className="procurement-meta">
                  <span
                    className={`status status-${procurement.status}`}
                  >
                    {procurement.status}
                  </span>

                  <ArrowRight size={18} />
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default Procurements
