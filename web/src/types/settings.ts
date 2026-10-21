export interface DiagnosticCheck {
  id: string
  label: string
  status: 'success' | 'warning' | 'error'
  detail: string
  action: string
  group: string
  required: boolean
}
export interface DiagnosticReport {
  demo?: boolean
  ready: boolean
  checks: DiagnosticCheck[]
}
