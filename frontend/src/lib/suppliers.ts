import type { Supplier } from '../types/supplier'

export function discoverSuppliers(): Supplier[] {
  return [
    {
      id: 'supplier-nordic-tech',
      name: 'Nordic Tech Supply',
      country: 'Sweden',
      website: 'https://example.com',
      description:
        'Business technology supplier focused on laptops and workplace equipment.',
      offers: [
        {
          id: 'offer-nordic-laptops',
          supplierId: 'supplier-nordic-tech',
          productName: 'Business Laptop Pro 14',
          description:
            'Business-class laptop suitable for software development and professional workloads.',
          price: '€1,180',
          currency: 'EUR',
          deliveryEstimate: '10–14 business days',
          warranty: '3 years',
          matches: [
            {
              requirementId: 'req-product',
              status: 'matched',
              value: 'Business laptop',
              evidenceIds: ['evidence-nordic-product'],
            },
            {
              requirementId: 'req-quantity',
              status: 'matched',
              value: '25 units available',
              evidenceIds: ['evidence-nordic-product'],
            },
            {
              requirementId: 'req-memory',
              status: 'matched',
              value: '16GB RAM',
              evidenceIds: ['evidence-nordic-product'],
            },
            {
              requirementId: 'req-storage',
              status: 'matched',
              value: '512GB SSD',
              evidenceIds: ['evidence-nordic-product'],
            },
            {
              requirementId: 'req-warranty',
              status: 'matched',
              value: '3 years',
              evidenceIds: ['evidence-nordic-warranty'],
            },
          ],
          evidence: [
            {
              id: 'evidence-nordic-product',
              type: 'product-page',
              title: 'Product specification',
              description:
                'Demo evidence representing the supplier product specification.',
            },
            {
              id: 'evidence-nordic-warranty',
              type: 'supplier-page',
              title: 'Warranty information',
              description:
                'Demo evidence representing supplier warranty information.',
            },
          ],
        },
      ],
    },
    {
      id: 'supplier-asia-business',
      name: 'Asia Business Systems',
      country: 'Singapore',
      website: 'https://example.com',
      description:
        'Technology procurement supplier serving business and engineering teams.',
      offers: [
        {
          id: 'offer-asia-laptops',
          supplierId: 'supplier-asia-business',
          productName: 'Engineering Notebook X',
          description:
            'Professional notebook configured for engineering and development workloads.',
          price: '€1,050',
          currency: 'EUR',
          deliveryEstimate: '14–21 business days',
          warranty: '2 years',
          matches: [
            {
              requirementId: 'req-product',
              status: 'matched',
              value: 'Business laptop',
              evidenceIds: ['evidence-asia-product'],
            },
            {
              requirementId: 'req-quantity',
              status: 'partial',
              value: '20 units currently listed',
              evidenceIds: ['evidence-asia-product'],
              note: 'Additional units may require a supplier quote.',
            },
            {
              requirementId: 'req-memory',
              status: 'matched',
              value: '16GB RAM',
              evidenceIds: ['evidence-asia-product'],
            },
            {
              requirementId: 'req-storage',
              status: 'matched',
              value: '512GB SSD',
              evidenceIds: ['evidence-asia-product'],
            },
            {
              requirementId: 'req-warranty',
              status: 'not-matched',
              value: '2 years',
              evidenceIds: ['evidence-asia-warranty'],
              note: 'Does not meet the requested 3-year warranty.',
            },
          ],
          evidence: [
            {
              id: 'evidence-asia-product',
              type: 'product-page',
              title: 'Product specification',
              description:
                'Demo evidence representing the supplier product specification.',
            },
            {
              id: 'evidence-asia-warranty',
              type: 'supplier-page',
              title: 'Warranty information',
              description:
                'Demo evidence representing supplier warranty information.',
            },
          ],
        },
      ],
    },
  ]
}
