import {
  ArrowLeft,
  Check,
  CircleAlert,
  ExternalLink,
  Search,
  Sparkles,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getProcurementById } from '../lib/procurement'
import { discoverSuppliers } from '../lib/suppliers'

function Suppliers() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const procurement = id ? getProcurementById(id) : undefined
  const suppliers = useMemo(() => discoverSuppliers(), [])

  const [selectedOffers, setSelectedOffers] = useState<string[]>([])

  if (!procurement) {
    return (
      <section className="page-section">
        <button
          className="text-button"
          onClick={() => navigate('/procurements')}
        >
          <ArrowLeft size={16} />
          Back to procurements
        </button>

        <div className="empty-state">
          <h1>Procurement not found</h1>
          <p>
            The procurement you are looking for no longer exists in this
            browser session.
          </p>
        </div>
      </section>
    )
  }

  const requirements = procurement.requirements

  function toggleOffer(offerId: string) {
    setSelectedOffers((current) =>
      current.includes(offerId)
        ? current.filter((id) => id !== offerId)
        : [...current, offerId],
    )
  }

  function compareSelected() {
    if (selectedOffers.length < 2 || !id) {
      return
    }

    const params = new URLSearchParams()
    params.set('offers', selectedOffers.join(','))

    navigate(`/procurements/${id}/compare?${params.toString()}`)
  }

  return (
    <section className="page-section">
      <div className="page-header">
        <button
          className="text-button"
          onClick={() => navigate(`/procurements/${procurement.id}`)}
        >
          <ArrowLeft size={16} />
          Back to procurement
        </button>

        <div className="eyebrow">
          <Search size={14} />
          SUPPLIER DISCOVERY
        </div>

        <h1>Find suppliers</h1>

        <p className="page-description">
          Supplier candidates matched against the approved procurement
          requirements.
        </p>
      </div>

      <div className="demo-banner">
        <Sparkles size={18} />

        <div>
          <strong>Demo discovery</strong>
          <p>
            These supplier candidates are demonstration data. Live supplier
            search, evidence and pricing will be connected later.
          </p>
        </div>
      </div>

      <div className="procurement-summary">
        <div>
          <span className="summary-label">PROCUREMENT</span>
          <h2>
            {procurement.title === 'New procurement'
              ? 'Engineering Team Laptops'
              : procurement.title}
          </h2>
          <p>{procurement.originalRequest}</p>
        </div>

        <div className="summary-stats">
          <div>
            <strong>{requirements.length}</strong>
            <span>requirements</span>
          </div>

          <div>
            <strong>{suppliers.length}</strong>
            <span>suppliers</span>
          </div>
        </div>
      </div>

      <div className="requirements-strip">
        {requirements.map((requirement) => (
          <div key={requirement.id} className="requirement-chip">
            <Check size={14} />
            <span>{requirement.name}</span>
            {requirement.value && <strong>{requirement.value}</strong>}
          </div>
        ))}
      </div>

      <div className="section-heading-row">
        <div>
          <span className="eyebrow">DISCOVERY RESULTS</span>
          <h2>Supplier candidates</h2>
          <p>
            Select at least two offers to compare them side by side.
          </p>
        </div>

        <button
          className="primary-button"
          disabled={selectedOffers.length < 2}
          onClick={compareSelected}
        >
          Compare selected
          {selectedOffers.length > 0 && (
            <span>({selectedOffers.length})</span>
          )}
        </button>
      </div>

      <div className="supplier-grid">
        {suppliers.map((supplier) =>
          supplier.offers.map((offer) => {
            const selected = selectedOffers.includes(offer.id)

            const matched = offer.matches.filter(
              (match) => match.status === 'matched',
            ).length

            return (
              <article
                key={offer.id}
                className={`supplier-card${selected ? ' supplier-card-selected' : ''}`}
              >
                <div className="supplier-card-top">
                  <div>
                    <span className="supplier-country">
                      {supplier.country}
                    </span>

                    <h3>{supplier.name}</h3>
                    <p className="offer-name">{offer.productName}</p>
                  </div>

                  <button
                    className={`select-offer${selected ? ' selected' : ''}`}
                    onClick={() => toggleOffer(offer.id)}
                    aria-pressed={selected}
                  >
                    {selected ? <Check size={16} /> : null}
                    {selected ? 'Selected' : 'Select'}
                  </button>
                </div>

                <div className="match-summary">
                  <Check size={15} />
                  {matched} of {requirements.length} requirements matched
                </div>

                <div className="offer-details">
                  <div>
                    <span>PRICE</span>
                    <strong>
                      {offer.price ?? 'Not available'}{' '}
                      {offer.currency ?? ''}
                    </strong>
                  </div>

                  <div>
                    <span>DELIVERY</span>
                    <strong>
                      {offer.deliveryEstimate ?? 'Not available'}
                    </strong>
                  </div>

                  <div>
                    <span>WARRANTY</span>
                    <strong>{offer.warranty ?? 'Not available'}</strong>
                  </div>
                </div>

                <div className="match-list">
                  {offer.matches.map((match) => {
                    const requirement = requirements.find(
                      (item) => item.id === match.requirementId,
                    )

                    const isMatched = match.status === 'matched'

                    return (
                      <div key={match.requirementId} className="match-row">
                        {isMatched ? (
                          <Check size={15} />
                        ) : (
                          <CircleAlert size={15} />
                        )}

                        <div>
                          <strong>
                            {requirement?.name ?? 'Requirement'}
                          </strong>

                          <span>
                            {match.value ??
                              match.note ??
                              'No matching evidence'}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>

                <div className="supplier-card-footer">
                  <a
                    href={supplier.website}
                    target="_blank"
                    rel="noreferrer"
                    className="text-button"
                  >
                    <ExternalLink size={15} />
                    View supplier
                  </a>
                </div>
              </article>
            )
          }),
        )}
      </div>

      <div className="demo-notice">
        <Sparkles size={16} />
        <span>
          Supplier results shown here are demonstration data, not live
          listings. Evidence and pricing will be connected to real supplier
          sources later.
        </span>
      </div>
    </section>
  )
}

export default Suppliers
