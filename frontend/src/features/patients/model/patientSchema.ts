import { z } from 'zod'

import type { Patient, PatientInput } from '@/shared/types'

export const patientSchema = z
  .object({
    full_name: z.string().trim().min(2, "Enter the patient's full name."),
    phone: z
      .string()
      .trim()
      .refine(
        (value) =>
          !value ||
          (value.replace(/\D/g, '').length >= 7 && value.replace(/\D/g, '').length <= 20),
        'Enter a phone number with 7 to 20 digits.',
      ),
    email: z
      .string()
      .trim()
      .refine(
        (value) => !value || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
        'Enter a valid email.',
      ),
    date_of_birth: z.string(),
    age_years: z
      .string()
      .refine(
        (value) =>
          !value || (/^\d+$/.test(value) && Number(value) >= 0 && Number(value) <= 130),
        'Age must be between 0 and 130.',
      ),
    sex: z.enum(['unknown', 'female', 'male', 'other']),
    notes: z.string(),
  })
  .superRefine((values, context) => {
    if (values.date_of_birth && values.age_years) {
      context.addIssue({
        code: 'custom',
        path: ['age_years'],
        message: 'Provide either a date of birth or an age, not both.',
      })
    }
    if (
      values.date_of_birth &&
      values.date_of_birth > new Date().toISOString().slice(0, 10)
    ) {
      context.addIssue({
        code: 'custom',
        path: ['date_of_birth'],
        message: 'Date of birth cannot be in the future.',
      })
    }
  })

export type PatientFormValues = z.infer<typeof patientSchema>

export function patientDefaults(patient?: Patient): PatientFormValues {
  return {
    full_name: patient?.full_name ?? '',
    phone: patient?.phone ?? '',
    email: patient?.email ?? '',
    date_of_birth: patient?.date_of_birth ?? '',
    age_years:
      patient?.age_years === null || patient?.age_years === undefined
        ? ''
        : String(patient.age_years),
    sex: patient?.sex ?? 'unknown',
    notes: patient?.notes ?? '',
  }
}

export function patientToInput(values: PatientFormValues): PatientInput {
  return {
    full_name: values.full_name.trim(),
    phone: values.phone.trim(),
    email: values.email.trim(),
    date_of_birth: values.date_of_birth || null,
    age_years: values.age_years ? Number(values.age_years) : null,
    sex: values.sex,
    notes: values.notes,
  }
}
