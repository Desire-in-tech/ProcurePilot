export type ProcurementStatus =
  | 'draft'
  | 'analyzing'
  | 'ready'
  | 'searching'
  | 'comparing'
  | 'completed'

export type RequirementPriority = 'required' | 'preferred'

export type RequirementCategory =
  | 'product'
  | 'quantity'
  | 'technical'
  | 'quality'
  | 'budget'
  | 'delivery'
  | 'supplier'
  | 'other'

export interface ProcurementRequirement {
  id: string
  category: RequirementCategory
  name: string
  description: string
  value?: string
  priority: RequirementPriority
}

export interface ProcurementConstraint {
  id: string
  name: string
  description: string
  value?: string
}

export interface ProcurementRequest {
  id: string
  title: string
  originalRequest: string
  status: ProcurementStatus
  requirements: ProcurementRequirement[]
  constraints: ProcurementConstraint[]
  missingInformation: string[]
  createdAt: string
  updatedAt: string
}
