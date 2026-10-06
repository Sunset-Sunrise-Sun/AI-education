import { afterEach, describe, expect, it, vi } from 'vitest'

import { loadCaseAOfferings, runCaseADemo } from '../src/api/caseADemo'

afterEach(() => vi.unstubAllGlobals())

describe('distinct Case A demo client', () => {
  it('loads only the Case A offerings endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await loadCaseAOfferings('2026-1')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/v1/case-a-demo/offerings')
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('/mock/')
  })

  it('binds the PDF, attestation, schedule and preference in one request', async () => {
    const payload = {
      transcript: { record_count: 1 }, makeup_tasks: [], course_offerings: [],
      preference: {}, plan_result: { status: 'feasible', selected_classes: [], changes: [], risks: [], unresolved: [] },
      provenance: { course_data: 'case-scoped:south+shenzhen', is_full_semester: false },
    }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const file = {
      name: 'transcript.pdf',
      type: 'application/pdf',
      arrayBuffer: async () => new Uint8Array([0x25, 0x50, 0x44, 0x46]).buffer,
    } as File
    await runCaseADemo({
      file,
      semester: '2026-1',
      currentSchedule: [],
      manualScheduleAttested: false,
      preference: {},
    })
    const options = fetchMock.mock.calls[0][1] as RequestInit
    const body = JSON.parse(String(options.body))
    expect(Object.keys(body).sort()).toEqual([
      'current_schedule', 'manual_schedule_attested', 'preference', 'semester', 'transcript_pdf_base64',
    ].sort())
    expect(body.transcript_pdf_base64).toBe('JVBERg==')
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('/mock/')
  })
})
