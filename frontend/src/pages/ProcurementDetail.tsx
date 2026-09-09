import { useMemo, useState } from 'react'
import {
  ArrowLeft,
  Check,
  CircleAlert,
  LoaderCircle,
  Pencil,
  Plus,
  Save,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  addRequirement,
  getProcurementById,
  removeRequirement,
  updateProcurement,
  updateRequirement,
  updateProcurementStatus,
} from '../lib/procurement'
import type {
  ProcurementRequest,
  ProcurementRequirement,
  RequirementCategory,
  RequirementPriority,
} from '../types/procurement'

const CATEGORY_OPTIONS: RequirementCategory[] = [
  'product',
  'quantity',
  'technical',
  'quality',
  'budget',
  'delivery',
  'supplier',
  'other',
]

const PRIORITY_OPTIONS: RequirementPriority[] = [
  'required',
  'preferred',
]

function ProcurementDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [procurement, setProcurement] = useState<
    ProcurementRequest | undefined
  >(() => (id ? getProcurementById(id) : undefined))

  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [isAdding, setIsAdding] = useState(false)

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
            This procurement may have been removed or the link may be
            invalid.
          </p>
        </section>
      </div>
    )
  }

  const procurementId = procurement.id

  function analyzeRequest() {
    if (isAnalyzing) {
      return
    }

    setIsAnalyzing(true)

    const analyzing = updateProcurementStatus(
      procurementId,
      'analyzing',
    )

    if (analyzing) {
      setProcurement(analyzing)
    }

    window.setTimeout(() => {
      const requirements: ProcurementRequirement[] = [
        {
          id: 'req-product',
          category: 'product',
          name: 'Product type',
          description:
            'Business laptops suitable for an engineering team',
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

      const ready = updateProcurement(procurementId, {
        status: 'ready',
        requirements,
        constraints: [],
        missingInformation: [
          'Preferred delivery date',
          'Delivery location',
          'Budget per unit',
        ],
      })

      if (ready) {
        setProcurement(ready)
      }

      setIsAnalyzing(false)
    }, 1000)
  }

  function handleRemoveRequirement(requirementId: string) {
    const updated = removeRequirement(
      procurementId,
      requirementId,
    )

    if (updated) {
      setProcurement(updated)
    }
  }

  function handleSaveRequirement(
    requirementId: string,
    values: {
      name: string
      description: string
      value: string
      category: RequirementCategory
      priority: RequirementPriority
    },
  ) {
    const updated = updateRequirement(
      procurementId,
      requirementId,
      {
        name: values.name.trim(),
        description: values.description.trim(),
        value: values.value.trim(),
        category: values.category,
        priority: values.priority,
      },
    )

    if (updated) {
      setProcurement(updated)
      setEditingId(null)
    }
  }

  function handleAddRequirement(values: {
    name: string
    description: string
    value: string
    category: RequirementCategory
    priority: RequirementPriority
  }) {
    if (!values.name.trim()) {
      return
    }

    const updated = addRequirement(procurementId, {
      name: values.name.trim(),
      description: values.description.trim(),
      value: values.value.trim(),
      category: values.category,
      priority: values.priority,
    })

    if (updated) {
      setProcurement(updated)
      setIsAdding(false)
    }
  }

  function approveAndFindSuppliers() {
    const updated = updateProcurementStatus(
      procurementId,
      'searching',
    )

    if (updated) {
      setProcurement(updated)
      navigate(`/procurements/${procurementId}/suppliers`)
    }
  }

  const groupedRequirements = useMemo(
    () =>
      procurement.requirements.reduce<
        Record<string, ProcurementRequirement[]>
      >((groups, requirement) => {
        if (!groups[requirement.category]) {
          groups[requirement.category] = []
        }

        groups[requirement.category].push(requirement)

        return groups
      }, {}),
    [procurement.requirements],
  )

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

        <span
          className={`status-badge status-${procurement.status}`}
        >
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
              ProcurePilot will identify products, quantities,
              technical requirements, constraints and missing
              information needed for supplier discovery.
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
            <LoaderCircle
              size={22}
              className="spin"
            />
          </div>

          <div className="analysis-content">
            <span className="eyebrow">
              ANALYZING REQUEST
            </span>

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
                <span className="eyebrow">
                  REQUIREMENT REVIEW
                </span>

                <h2>Review what ProcurePilot understood</h2>

                <p>
                  Check the extracted requirements before supplier
                  discovery. You can edit, remove or add anything
                  that is missing.
                </p>
              </div>

              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setEditingId(null)
                  setIsAdding(true)
                }}
                disabled={isAdding}
              >
                <Plus size={16} />
                Add requirement
              </button>
            </div>

            {isAdding && (
              <RequirementEditor
                title="New requirement"
                onCancel={() => setIsAdding(false)}
                onSave={handleAddRequirement}
              />
            )}

            <div className="requirements-list">
              {Object.entries(groupedRequirements).map(
                ([category, requirements]) => (
                  <div
                    className="requirement-group"
                    key={category}
                  >
                    <span className="requirement-category">
                      {category}
                    </span>

                    {requirements.map((requirement) =>
                      editingId === requirement.id ? (
                        <RequirementEditor
                          key={requirement.id}
                          title="Edit requirement"
                          initialValues={{
                            name: requirement.name,
                            description:
                              requirement.description,
                            value: requirement.value ?? '',
                            category: requirement.category,
                            priority: requirement.priority,
                          }}
                          onCancel={() =>
                            setEditingId(null)
                          }
                          onSave={(values) =>
                            handleSaveRequirement(
                              requirement.id,
                              values,
                            )
                          }
                        />
                      ) : (
                        <RequirementRow
                          key={requirement.id}
                          requirement={requirement}
                          onEdit={() =>
                            setEditingId(requirement.id)
                          }
                          onRemove={() =>
                            handleRemoveRequirement(
                              requirement.id,
                            )
                          }
                        />
                      ),
                    )}
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
                <span className="eyebrow">
                  INFORMATION STILL NEEDED
                </span>

                <h2>
                  Complete these details before supplier
                  discovery
                </h2>

                <ul>
                  {procurement.missingInformation.map(
                    (item) => (
                      <li key={item}>{item}</li>
                    ),
                  )}
                </ul>

                <p className="missing-note">
                  These are not currently part of the structured
                  requirements. They can be added as procurement
                  details when the backend workflow is connected.
                </p>
              </div>
            </section>
          )}

          {procurement.status === 'ready' && (
            <section className="approval-card">
              <div>
                <span className="eyebrow">
                  REQUIREMENTS READY
                </span>

                <h2>Ready to discover suppliers?</h2>

                <p>
                  ProcurePilot will use these reviewed requirements
                  to evaluate supplier offers.
                </p>
              </div>

              <button
                type="button"
                className="primary-button"
                onClick={approveAndFindSuppliers}
                disabled={procurement.requirements.length === 0}
              >
                <Check size={17} />
                Approve & find suppliers
              </button>
            </section>
          )}
        </>
      )}
    </div>
  )
}

interface RequirementRowProps {
  requirement: ProcurementRequirement
  onEdit: () => void
  onRemove: () => void
}

function RequirementRow({
  requirement,
  onEdit,
  onRemove,
}: RequirementRowProps) {
  return (
    <div className="requirement-row">
      <div className="requirement-check">
        <Check size={15} />
      </div>

      <div className="requirement-main">
        <strong>{requirement.name}</strong>
        <span>{requirement.description}</span>
      </div>

      <div className="requirement-value">
        <strong>{requirement.value || 'Not specified'}</strong>

        <span
          className={`priority priority-${requirement.priority}`}
        >
          {requirement.priority}
        </span>
      </div>

      <div className="requirement-actions">
        <button
          type="button"
          className="icon-button"
          onClick={onEdit}
          aria-label={`Edit ${requirement.name}`}
          title="Edit requirement"
        >
          <Pencil size={15} />
        </button>

        <button
          type="button"
          className="icon-button danger"
          onClick={onRemove}
          aria-label={`Remove ${requirement.name}`}
          title="Remove requirement"
        >
          <Trash2 size={15} />
        </button>
      </div>
    </div>
  )
}

interface RequirementEditorProps {
  title: string
  initialValues?: {
    name: string
    description: string
    value: string
    category: RequirementCategory
    priority: RequirementPriority
  }
  onCancel: () => void
  onSave: (values: {
    name: string
    description: string
    value: string
    category: RequirementCategory
    priority: RequirementPriority
  }) => void
}

function RequirementEditor({
  title,
  initialValues = {
    name: '',
    description: '',
    value: '',
    category: 'other',
    priority: 'required',
  },
  onCancel,
  onSave,
}: RequirementEditorProps) {
  const [name, setName] = useState(initialValues.name)
  const [description, setDescription] = useState(
    initialValues.description,
  )
  const [value, setValue] = useState(initialValues.value)
  const [category, setCategory] = useState(
    initialValues.category,
  )
  const [priority, setPriority] = useState(
    initialValues.priority,
  )

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()

    if (!name.trim()) {
      return
    }

    onSave({
      name,
      description,
      value,
      category,
      priority,
    })
  }

  return (
    <form
      className="requirement-editor"
      onSubmit={handleSubmit}
    >
      <div className="requirement-editor-header">
        <div>
          <span className="eyebrow">REQUIREMENT</span>
          <h3>{title}</h3>
        </div>

        <button
          type="button"
          className="icon-button"
          onClick={onCancel}
          aria-label="Cancel"
          title="Cancel"
        >
          <X size={17} />
        </button>
      </div>

      <div className="requirement-editor-grid">
        <label>
          Name
          <input
            value={name}
            onChange={(event) =>
              setName(event.target.value)
            }
            placeholder="e.g. Processor"
            required
          />
        </label>

        <label>
          Value
          <input
            value={value}
            onChange={(event) =>
              setValue(event.target.value)
            }
            placeholder="e.g. Intel Core i7"
          />
        </label>

        <label>
          Category
          <select
            value={category}
            onChange={(event) =>
              setCategory(
                event.target.value as RequirementCategory,
              )
            }
          >
            {CATEGORY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label>
          Priority
          <select
            value={priority}
            onChange={(event) =>
              setPriority(
                event.target.value as RequirementPriority,
              )
            }
          >
            {PRIORITY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="full-width">
          Description
          <textarea
            value={description}
            onChange={(event) =>
              setDescription(event.target.value)
            }
            placeholder="Describe what the supplier needs to satisfy."
            rows={3}
          />
        </label>
      </div>

      <div className="requirement-editor-actions">
        <button
          type="button"
          className="secondary-button"
          onClick={onCancel}
        >
          <X size={15} />
          Cancel
        </button>

        <button
          type="submit"
          className="primary-button"
        >
          <Save size={15} />
          Save requirement
        </button>
      </div>
    </form>
  )
}

export default ProcurementDetail
