import type {
  ProcurementRequest,
  ProcurementStatus,
} from '../types/procurement'

const STORAGE_KEY = 'procurepilot.procurements'

function generateId(): string {
  return `proc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function getStoredProcurements(): ProcurementRequest[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)

    if (!stored) {
      return []
    }

    return JSON.parse(stored) as ProcurementRequest[]
  } catch {
    return []
  }
}

function saveProcurements(procurements: ProcurementRequest[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(procurements))
}

export function getProcurements(): ProcurementRequest[] {
  return getStoredProcurements()
}

export function getProcurementById(
  id: string,
): ProcurementRequest | undefined {
  return getStoredProcurements().find(
    (procurement) => procurement.id === id,
  )
}

function generateProcurementTitle(request: string): string {
  const normalized = request.trim()

  if (/laptop/i.test(normalized)) {
    return 'Engineering Team Laptops'
  }

  if (/monitor/i.test(normalized)) {
    return 'Business Monitors'
  }

  if (/software|license/i.test(normalized)) {
    return 'Software Procurement'
  }

  const words = normalized
    .replace(/[^a-zA-Z0-9\s-]/g, '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 5)

  if (words.length === 0) {
    return 'New procurement'
  }

  const title = words.join(' ')

  return title.charAt(0).toUpperCase() + title.slice(1)
}

export function createProcurement(
  originalRequest: string,
): ProcurementRequest {
  const now = new Date().toISOString()

  const procurement: ProcurementRequest = {
    id: generateId(),
    title: generateProcurementTitle(originalRequest),
    originalRequest: originalRequest.trim(),
    status: 'draft',
    requirements: [],
    constraints: [],
    missingInformation: [],
    createdAt: now,
    updatedAt: now,
  }

  const procurements = getStoredProcurements()

  saveProcurements([procurement, ...procurements])

  return procurement
}

export function updateProcurementStatus(
  id: string,
  status: ProcurementStatus,
): ProcurementRequest | undefined {
  const procurements = getStoredProcurements()

  const index = procurements.findIndex(
    (procurement) => procurement.id === id,
  )

  if (index === -1) {
    return undefined
  }

  const updated: ProcurementRequest = {
    ...procurements[index],
    status,
    updatedAt: new Date().toISOString(),
  }

  procurements[index] = updated

  saveProcurements(procurements)

  return updated
}
