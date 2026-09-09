export type SupplierMatchStatus =
  | 'matched'
  | 'partial'
  | 'unknown'
  | 'not-matched'

export type EvidenceType =
  | 'product-page'
  | 'supplier-page'
  | 'document'
  | 'other'

export interface SupplierEvidence {
  id: string
  type: EvidenceType
  title: string
  url?: string
  description?: string
}

export interface SupplierRequirementMatch {
  requirementId: string
  status: SupplierMatchStatus
  value?: string
  evidenceIds: string[]
  note?: string
}

export interface SupplierOffer {
  id: string
  supplierId: string
  productName: string
  description: string
  price?: string
  currency?: string
  deliveryEstimate?: string
  warranty?: string
  matches: SupplierRequirementMatch[]
  evidence: SupplierEvidence[]
}

export interface Supplier {
  id: string
  name: string
  country: string
  website?: string
  description: string
  offers: SupplierOffer[]
}
