import {
  ArrowLeft,
  Check,
  CircleAlert,
  ExternalLink,
  Sparkles,
} from 'lucide-react'
import { useMemo } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { getProcurementById } from '../lib/procurement'
import { discoverSuppliers } from '../lib/suppliers'

function SupplierCompare() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const procurement = id ? getProcurementById(id) : undefined
  const suppliers = useMemo(() => discoverSuppliers(), [])

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

  const selectedIds =
    searchParams.get('offers')?.split(',').filter(Boolean) ?? []

  const selectedOffers = suppliers.flatMap((supplier) =>
    supplier.offers
      .filter((offer) => selectedIds.includes(offer.id))
      .map((offer) => ({
        supplier,
        offer,
      })),
  )

  const offersToShow =
    selectedOffers.length >= 2
      ? selectedOffers
      : suppliers.flatMap((supplier) =>
          supplier.offers.map((offer) => ({
            supplier,
            offer,
          })),
        )

  return (
    <section className="page-section">
      <div className="page-header">
        <button
          className="text-button"
          onClick={() => navigate(`/procurements/${procurement.id}/suppliers`)}
        >
          <ArrowLeft size={16} />
          Back to suppliers
        </button>

        <div className="eyebrow">SUPPLIER COMPARISON</div>

        <h1>Compare offers</h1>

        <p className="page-description">
          Compare supplier offers against the approved requirements.
        </p>
      </div>

      <div className="demo-banner">
        <Sparkles size={18} />

        <div>
          <strong>Demo comparison</strong>
          <p>
            Comparison is based on demonstration supplier data. Live supplier
            evidence and pricing will be connected later.
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
      </div>

      {selectedOffers.length < 2 && (
        <div className="comparison-warning">
          <CircleAlert size={18} />
          <div>
            <strong>Select at least two offers</strong>
            <p>
              Go back to supplier discovery and select two or more offers for
              a true side-by-side comparison.
            </p>
          </div>

          <button
            className="secondary-button"
            onClick={() =>
              navigate(`/procurements/${procurement.id}/suppliers`)
            }
          >
            Select suppliers
          </button>
        </div>
      )}

      <div className="comparison-wrapper">
        <table className="comparison-table">
          <thead>
            <tr>
              <th>Requirement</th>

              {offersToShow.map(({ supplier, offer }) => (
                <th key={offer.id}>
                  <div className="comparison-supplier">
                    <span>{supplier.country}</span>
                    <strong>{supplier.name}</strong>
                    <small>{offer.productName}</small>
                  </div>
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {procurement.requirements.map((requirement) => (
              <tr key={requirement.id}>
                <td>
                  <strong>{requirement.name}</strong>

                  {requirement.value && (
                    <span>{requirement.value}</span>
                  )}
                </td>

                {offersToShow.map(({ offer }) => {
                  const match = offer.matches.find(
                    (item) => item.requirementId === requirement.id,
                  )

                  const isMatched = match?.status === 'matched'

                  return (
                    <td key={`${offer.id}-${requirement.id}`}>
                      <div
                        className={`comparison-match comparison-${match?.status ?? 'unknown'}`}
                      >
                        {isMatched ? (
                          <Check size={16} />
                        ) : (
                          <CircleAlert size={16} />
                        )}

                        <div>
                          <strong>
                            {match?.status === 'matched'
                              ? 'Matched'
                              : match?.status === 'partial'
                                ? 'Partial'
                                : match?.status === 'not-matched'
                                  ? 'Not matched'
                                  : 'Unknown'}
                          </strong>

                          <span>
                            {match?.value ??
                              match?.note ??
                              'No evidence available'}
                          </span>
                        </div>
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}

            <tr className="comparison-summary-row">
              <td>
                <strong>Offer summary</strong>
              </td>

              {offersToShow.map(({ supplier, offer }) => (
                <td key={offer.id}>
                  <div className="comparison-offer-summary">
                    <strong>
                      {offer.price ?? 'Price unavailable'}{' '}
                      {offer.currency ?? ''}
                    </strong>

                    <span>
                      Delivery:{' '}
                      {offer.deliveryEstimate ?? 'Not available'}
                    </span>

                    <span>
                      Warranty: {offer.warranty ?? 'Not available'}
                    </span>

                    <a
                      href={supplier.website}
                      target="_blank"
                      rel="noreferrer"
                      className="text-button"
                    >
                      <ExternalLink size={14} />
                      View supplier
                    </a>
                  </div>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="demo-notice">
        <Sparkles size={16} />
        <span>
          This comparison uses demonstration supplier offers. No prices,
          availability or supplier evidence shown here should be interpreted
          as live procurement information.
        </span>
      </div>
    </section>
  )
}

export default SupplierCompare
