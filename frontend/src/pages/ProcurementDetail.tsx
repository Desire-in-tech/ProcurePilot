import { useState } from 'react'
import {
  ArrowLeft,
  Check,
  CircleAlert,
  LoaderCircle,
  Plus,
  Sparkles,
} from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  getProcurementById,
  getProcurements,
  updateProcurementStatus,
} from '../lib/procurement'
import type {
  ProcurementRequest,
  ProcurementRequirement,
} from '../types/procurement'

function ProcurementDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [procurement, setProcurement] = useState<ProcurementRequest | undefined>(
    () => (id ? getProcurementById(id) : undefined),
  )
  const [isAnalyzing, setIsAnalyzing] = useState(false)

  if (!procurement) {
    return (
      <div className="page">
        <Link to="/procurements" className="back-link">
          <ArrowLeft size={17} />
          Back to procurements
        </Link>

        <section className="empty-state">
          <h1>Procurement not found</h1>
          <p>
            This procurement may have been removed or the link may be invalid.
          </p>
        </section>
      </div>
    )
  }

  const analyzeRequest = () => {
    if (isAnalyzing) {
      return
    }

    setIsAnalyzing(true)

    const analyzing = updateProcurementStatus(procurement.id, 'analyzing')

    if (analyzing) {
      setProcurement(analyzing)
    }

    window.setTimeout(() => {
      const requirements: ProcurementRequirement[] = [
        {
          id: 'req-product',
          category: 'product',
          name: 'Product type',
          description: 'Business laptops suitable for an engineering team',
          value: 'Business laptops',
          priority: 'required',
        },
        {
          id: 'req-quantity',
          category: 'quantity',
          name: 'Quantity',
          description: 'Number of laptops required',
          value: '25 units',
          priority: 'required',
        },
        {
          id: 'req-memory',
          category: 'technical',
          name: 'Memory',
          description: 'Minimum RAM capacity',
          value: '16GB RAM',
          priority: 'required',
        },
        {
          id: 'req-storage',
          category: 'technical',
          name: 'Storage',
          description: 'Minimum storage capacity',
          value: '512GB SSD',
          priority: 'required',
        },
        {
          id: 'req-warranty',
          category: 'quality',
          name: 'Warranty',
          description: 'Minimum warranty period',
          value: '3 years',
          priority: 'required',
        },
      ]

      const ready: ProcurementRequest = {
        ...procurement,
        status: 'ready',
        requirements,
        constraints: [],
        missingInformation: [
          'Preferred delivery date',
          'Delivery location',
          'Budget per unit',
        ],
        updatedAt: new Date().toISOString(),
      }

      localStorage.setItem(
        'procurepilot.procurements',
        JSON.stringify([
          ready,
          ...getProcurementsExcept(ready.id),
        ]),
      )

      setProcurement(ready)
      setIsAnalyzing(false)
    }, 1000)
  }

  const approveAndFindSuppliers = () => {
    const updated = updateProcurementStatus(
      procurement.id,
      'searching',
    )

    if (updated) {
      setProcurement(updated)
      navigate(`/procurements/${procurement.id}/suppliers`)
    }
  }

  const groupedRequirements = procurement.requirements.reduce<
    Record<string, ProcurementRequirement[]>
  >((groups, requirement) => {
    if (!groups[requirement.category]) {
      groups[requirement.category] = []
    }

    groups[requirement.category].push(requirement)

    return groups
  }, {})

  return (
    <div className="page">
      <Link to="/procurements" className="back-link">
        <ArrowLeft size={17} />
        Back to procurements
      </Link>

      <div className="page-header">
        <div>
          <span className="eyebrow">PROCUREMENT REQUEST</span>
          <h1>{procurement.title}</h1>
        </div>

        <span className={`status-badge status-${procurement.status}`}>
          {procurement.status}
        </span>
      </div>

      <section className="request-card">
        <div className="section-heading">
          <div>
            <span className="eyebrow">ORIGINAL REQUEST</span>
            <h2>What you asked for</h2>
          </div>
        </div>

        <p className="original-request">
          {procurement.originalRequest}
        </p>
      </section>

      {procurement.status === 'draft' && (
        <section className="analysis-card">
          <div className="analysis-icon">
            <Sparkles size={22} />
          </div>

          <div className="analysis-content">
            <span className="eyebrow">AGENT ANALYSIS</span>
            <h2>Turn the request into requirements</h2>
            <p>
              ProcurePilot will identify the products, quantities,
              technical requirements, constraints and missing information
              needed for supplier discovery.
            </p>

            <button
              type="button"
              className="primary-button agent-action"
              onClick={analyzeRequest}
              disabled={isAnalyzing}
            >
              <Sparkles size={17} />
              Analyze request
            </button>
          </div>
        </section>
      )}

      {procurement.status === 'analyzing' && (
        <section className="analysis-card">
          <div className="analysis-icon">
            <LoaderCircle size={22} className="spin" />
          </div>

          <div className="analysis-content">
            <span className="eyebrow">ANALYZING REQUEST</span>
            <h2>Understanding what you need...</h2>
            <p>
              ProcurePilot is extracting structured procurement
              requirements from your request.
            </p>

            <div className="analysis-loading">
              <div className="loading-line" />
              <div className="loading-line short" />
              <div className="loading-line" />
            </div>
          </div>
        </section>
      )}

      {procurement.requirements.length > 0 && (
        <>
          <section className="request-card">
            <div className="section-heading">
              <div>
                <span className="eyebrow">STRUCTURED REQUIREMENTS</span>
                <h2>What ProcurePilot understood</h2>
              </div>

              <button type="button" className="secondary-button">
                <Plus size={16} />
                Add requirement
              </button>
            </div>

            <div className="requirements-list">
              {Object.entries(groupedRequirements).map(
                ([category, requirements]) => (
                  <div className="requirement-group" key={category}>
                    <span className="requirement-category">
                      {category}
                    </span>

                    {requirements.map((requirement) => (
                      <div
                        className="requirement-row"
                        key={requirement.id}
                      >
                        <div className="requirement-check">
                          <Check size={15} />
                        </div>

                        <div className="requirement-main">
                          <strong>{requirement.name}</strong>
                          <span>{requirement.description}</span>
                        </div>

                        <div className="requirement-value">
                          <strong>{requirement.value}</strong>
                          <span
                            className={`priority priority-${requirement.priority}`}
                          >
                            {requirement.priority}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ),
              )}
            </div>
          </section>

          {procurement.missingInformation.length > 0 && (
            <section className="missing-card">
              <div className="missing-icon">
                <CircleAlert size={20} />
              </div>

              <div>
                <span className="eyebrow">INFORMATION STILL NEEDED</span>
                <h2>Complete these details before supplier discovery</h2>

                <ul>
                  {procurement.missingInformation.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </section>
          )}

          {procurement.status === 'ready' && (
            <div className="detail-actions">
              <button
                type="button"
                className="primary-button"
                onClick={approveAndFindSuppliers}
              >
                <Sparkles size={17} />
                Approve & find suppliers
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function getProcurementsExcept(id: string): ProcurementRequest[] {
  return getProcurements().filter(
    (procurement) => procurement.id !== id,
  )
}

export default ProcurementDetail
