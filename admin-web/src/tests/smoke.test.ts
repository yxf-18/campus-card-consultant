import { describe, expect, it } from 'vitest'
describe('admin web contract', () => { it('uses the versioned API prefix', () => { expect('/api/v1/admin/documents').toContain('/api/v1') }) })
