# Eval Report: Test Cases Execution

## TC001: Wrong Document Uploaded
**Produced Decision:** STOPPED EARLY (Validation Error)
**Error Message:**
```
UNREADABLE_DOCUMENT: We could not clearly read the uploaded document(s). Please ensure the image is clear, well-lit, and the entire document is visible, then re-upload.
```

**Expected Outcome:** {
  "decision": null,
  "system_must": [
    "Stop before making any claim decision",
    "Tell the member specifically what document type was uploaded and what is needed instead",
    "Not return a generic error \u00e2\u20ac\u201d the message must name the uploaded document type and the required document type"
  ]
}
---

## TC002: Unreadable Document
**Produced Decision:** STOPPED EARLY (Validation Error)
**Error Message:**
```
UNREADABLE_DOCUMENT: We could not clearly read the uploaded document(s). Please ensure the image is clear, well-lit, and the entire document is visible, then re-upload.
```

**Expected Outcome:** {
  "decision": null,
  "system_must": [
    "Identify that the pharmacy bill cannot be read",
    "Ask the member to re-upload that specific document",
    "Not reject the claim outright"
  ]
}
---

## TC003: Documents Belong to Different Patients
**Produced Decision:** STOPPED EARLY (Validation Error)
**Error Message:**
```
UNREADABLE_DOCUMENT: We could not clearly read the uploaded document(s). Please ensure the image is clear, well-lit, and the entire document is visible, then re-upload.
```

**Expected Outcome:** {
  "decision": null,
  "system_must": [
    "Detect that the documents belong to different people",
    "Surface this to the member with the specific names found on each document",
    "Not proceed to a claim decision"
  ]
}
---

## TC004: Clean Consultation â€” Full Approval
**Produced Decision:** APPROVED
**Approved Amount:** ₹1350.0
**Reasons:** Applied 10.0% co-pay
**Adjustments:** 
**Confidence:** 1.0
**Trace (Verifier Output):**
```json
{
  "extracted_fields": {
    "Doctor Name": "Dr. Arun Sharma",
    "Doctor Registration Number": "KA/45678/2015",
    "Hospital / Clinic Name": "City Clinic, Bengaluru",
    "Patient Name": "Rajesh Kumar",
    "All Patient Names": "Rajesh Kumar",
    "Date": "2024-11-01",
    "Diagnosis": "Viral Fever",
    "Medicines": "Paracetamol 650mg, Vitamin C 500mg",
    "Tests Ordered": "CBC Test, Dengue NS1 Test"
  },
  "trace_data": [
    {
      "agent": "Document Verifier (LLM)",
      "status": "SUCCESS",
      "output": {
        "document_type": "PRESCRIPTION",
        "key_fields": {
          "Doctor Name": "Dr. Arun Sharma",
          "Doctor Registration Number": "KA/45678/2015",
          "Hospital / Clinic Name": "City Clinic, Bengaluru",
          "Patient Name": "Rajesh Kumar",
          "All Patient Names": "Rajesh Kumar",
          "Date": "2024-11-01",
          "Diagnosis": "Viral Fever",
          "Medicines": "Paracetamol 650mg, Vitamin C 500mg",
          "Tests Ordered": "CBC Test, Dengue NS1 Test"
        },
        "confidence": 1.0,
        "flags": [],
        "warnings": [],
        "detected_doc_types": [
          "PRESCRIPTION",
          "HOSPITAL_BILL"
        ],
        "required_doc_types": [
          "PRESCRIPTION",
          "HOSPITAL_BILL"
        ]
      },
      "duration_ms": 3346
    }
  ]
}
```

**Expected Outcome:** {
  "decision": "APPROVED",
  "approved_amount": 1350,
  "notes": "10% co-pay applied on consultation category (\u00e2\u201a\u00b9150 deducted)",
  "confidence_score": "above 0.85"
}
---

## TC005: Waiting Period â€” Diabetes
**Produced Decision:** REJECTED
**Approved Amount:** ₹0.0
**Reasons:** WAITING_PERIOD: Waiting period for diabetes not completed. Eligible after 90 days from joining.
**Adjustments:** 
**Confidence:** 1.0
**Trace (Verifier Output):**
```json
{
  "extracted_fields": {
    "Doctor Name": "Dr. Sunil Mehta",
    "Doctor Registration Number": "GJ/56789/2014",
    "Patient Name": "Vikram Joshi",
    "All Patient Names": "Vikram Joshi",
    "Date": "2024-10-15",
    "Diagnosis": "Type 2 Diabetes Mellitus",
    "Medicines": "Metformin 500mg, Glimepiride 1mg"
  },
  "trace_data": [
    {
      "agent": "Document Verifier (LLM)",
      "status": "SUCCESS",
      "output": {
        "document_type": "PRESCRIPTION",
        "key_fields": {
          "Doctor Name": "Dr. Sunil Mehta",
          "Doctor Registration Number": "GJ/56789/2014",
          "Patient Name": "Vikram Joshi",
          "All Patient Names": "Vikram Joshi",
          "Date": "2024-10-15",
          "Diagnosis": "Type 2 Diabetes Mellitus",
          "Medicines": "Metformin 500mg, Glimepiride 1mg"
        },
        "confidence": 1.0,
        "flags": [],
        "warnings": [],
        "detected_doc_types": [
          "PRESCRIPTION",
          "HOSPITAL_BILL"
        ],
        "required_doc_types": [
          "PRESCRIPTION",
          "HOSPITAL_BILL"
        ]
      },
      "duration_ms": 3226
    }
  ]
}
```

**Expected Outcome:** {
  "decision": "REJECTED",
  "rejection_reasons": [
    "WAITING_PERIOD"
  ],
  "system_must": [
    "State the date from which the member will be eligible for diabetes-related claims"
  ]
}
---

## TC006: Dental Partial Approval â€” Cosmetic Exclusion
**Produced Decision:** PARTIAL
**Approved Amount:** ₹8000.0
**Reasons:** Applied policy limit (category sub-limit or per-claim limit), LLM Flagged Line-Item Exclusion: Teeth Whitening - Cosmetic dental procedures (-4000.0)
**Adjustments:** 
**Confidence:** 0.9
**Trace (Verifier Output):**
```json
{
  "extracted_fields": {
    "Hospital Name": "Smile Dental Clinic",
    "Patient Name": "Priya Singh",
    "All Patient Names": "Priya Singh",
    "Line Items": "Root Canal Treatment 8000, Teeth Whitening 4000",
    "Subtotal": "12000",
    "Total Amount": "12000"
  },
  "trace_data": [
    {
      "agent": "Document Verifier (LLM)",
      "status": "SUCCESS",
      "output": {
        "document_type": "HOSPITAL_BILL",
        "key_fields": {
          "Hospital Name": "Smile Dental Clinic",
          "Patient Name": "Priya Singh",
          "All Patient Names": "Priya Singh",
          "Line Items": "Root Canal Treatment 8000, Teeth Whitening 4000",
          "Subtotal": "12000",
          "Total Amount": "12000"
        },
        "confidence": 1.0,
        "flags": [],
        "warnings": [],
        "detected_doc_types": [
          "HOSPITAL_BILL"
        ],
        "required_doc_types": [
          "HOSPITAL_BILL"
        ]
      },
      "duration_ms": 2896
    }
  ]
}
```

**Expected Outcome:** {
  "decision": "PARTIAL",
  "approved_amount": 8000,
  "system_must": [
    "Itemize which line items were approved and which were rejected",
    "State the reason for each rejection at the line-item level"
  ]
}
---

## TC007: MRI Without Pre-Authorization
**Produced Decision:** REJECTED
**Approved Amount:** ₹0.0
**Reasons:** WAITING_PERIOD: Waiting period for hernia not completed. Eligible after 365 days from joining., LLM Flagged Line-Item Exclusion: MRI Lumbar Spine - Exceeds per-claim limit (-15000.0)
**Adjustments:** 
**Confidence:** 0.9
**Trace (Verifier Output):**
```json
{
  "extracted_fields": {
    "Line Items": "MRI Lumbar Spine 15000",
    "Subtotal": "15000",
    "Total Amount": "15000"
  },
  "trace_data": [
    {
      "agent": "Document Verifier (LLM)",
      "status": "SUCCESS",
      "output": {
        "document_type": "HOSPITAL_BILL",
        "key_fields": {
          "Line Items": "MRI Lumbar Spine 15000",
          "Subtotal": "15000",
          "Total Amount": "15000"
        },
        "confidence": 1.0,
        "flags": [],
        "warnings": [],
        "detected_doc_types": [
          "PRESCRIPTION",
          "DIAGNOSTIC_REPORT",
          "HOSPITAL_BILL"
        ],
        "required_doc_types": [
          "PRESCRIPTION",
          "DIAGNOSTIC_REPORT",
          "HOSPITAL_BILL"
        ]
      },
      "duration_ms": 4340
    }
  ]
}
```

**Expected Outcome:** {
  "decision": "REJECTED",
  "rejection_reasons": [
    "PRE_AUTH_MISSING"
  ],
  "system_must": [
    "Explain that pre-authorization was required and not obtained",
    "Tell the member what they should do to resubmit with pre-auth"
  ]
}
---

## TC008: Per-Claim Limit Exceeded
**Produced Decision:** REJECTED
**Approved Amount:** ₹0.0
**Reasons:** PER_CLAIM_EXCEEDED: Claimed amount (7500.0) exceeds per-claim limit of 5000.0
**Adjustments:** 
**Confidence:** 1.0
**Trace (Verifier Output):**
```json
{
  "extracted_fields": {
    "Doctor Name": "Dr. R. Gupta",
    "Doctor Registration Number": "DL/34567/2016",
    "Diagnosis": "Gastroenteritis",
    "Medicines": "Antibiotics, Probiotics, ORS"
  },
  "trace_data": [
    {
      "agent": "Document Verifier (LLM)",
      "status": "SUCCESS",
      "output": {
        "document_type": "PRESCRIPTION",
        "key_fields": {
          "Doctor Name": "Dr. R. Gupta",
          "Doctor Registration Number": "DL/34567/2016",
          "Diagnosis": "Gastroenteritis",
          "Medicines": "Antibiotics, Probiotics, ORS"
        },
        "confidence": 1.0,
        "flags": [],
        "warnings": [],
        "detected_doc_types": [
          "PRESCRIPTION",
          "HOSPITAL_BILL"
        ],
        "required_doc_types": [
          "PRESCRIPTION",
          "HOSPITAL_BILL"
        ]
      },
      "duration_ms": 2623
    }
  ]
}
```

**Expected Outcome:** {
  "decision": "REJECTED",
  "rejection_reasons": [
    "PER_CLAIM_EXCEEDED"
  ],
  "system_must": [
    "State the per-claim limit and the claimed amount clearly in the rejection message"
  ]
}
---

## TC009: Fraud Signal â€” Multiple Same-Day Claims
**Produced Decision:** STOPPED EARLY (Validation Error)
**Error Message:**
```
UNREADABLE_DOCUMENT: We could not clearly read the uploaded document(s). Please ensure the image is clear, well-lit, and the entire document is visible, then re-upload.
```

**Expected Outcome:** {
  "decision": "MANUAL_REVIEW",
  "system_must": [
    "Flag the unusual same-day claim pattern",
    "Route to manual review rather than auto-rejecting",
    "Include the specific signals that triggered the flag in the output"
  ]
}
---

## TC010: Network Hospital â€” Discount Applied
**Produced Decision:** APPROVED
**Approved Amount:** ₹3240.0
**Reasons:** Applied 10.0% co-pay, Network hospital discount applied
**Adjustments:** 
**Confidence:** 1.0
**Trace (Verifier Output):**
```json
{
  "extracted_fields": {
    "Doctor Name": "Dr. S. Iyer",
    "Doctor Registration Number": "TN/56789/2013",
    "Hospital / Clinic Name": "Apollo Hospitals",
    "Patient Name": "Deepak Shah",
    "All Patient Names": "Deepak Shah",
    "Diagnosis": "Acute Bronchitis",
    "Medicines": "Amoxicillin 500mg, Salbutamol Inhaler"
  },
  "trace_data": [
    {
      "agent": "Document Verifier (LLM)",
      "status": "SUCCESS",
      "output": {
        "document_type": "PRESCRIPTION",
        "key_fields": {
          "Doctor Name": "Dr. S. Iyer",
          "Doctor Registration Number": "TN/56789/2013",
          "Hospital / Clinic Name": "Apollo Hospitals",
          "Patient Name": "Deepak Shah",
          "All Patient Names": "Deepak Shah",
          "Diagnosis": "Acute Bronchitis",
          "Medicines": "Amoxicillin 500mg, Salbutamol Inhaler"
        },
        "confidence": 1.0,
        "flags": [],
        "warnings": [],
        "detected_doc_types": [
          "PRESCRIPTION",
          "HOSPITAL_BILL"
        ],
        "required_doc_types": [
          "PRESCRIPTION",
          "HOSPITAL_BILL"
        ]
      },
      "duration_ms": 3337
    }
  ]
}
```

**Expected Outcome:** {
  "decision": "APPROVED",
  "approved_amount": 3240,
  "notes": "Network discount (20%) applied first on \u00e2\u201a\u00b94,500 = \u00e2\u201a\u00b93,600. Co-pay (10%) applied on \u00e2\u201a\u00b93,600 = \u00e2\u201a\u00b9360 deducted. Final: \u00e2\u201a\u00b93,240.",
  "system_must": [
    "Apply network discount before co-pay, not after",
    "Show the breakdown of discount and co-pay in the decision output"
  ]
}
---

## TC011: Component Failure â€” Graceful Degradation
**Produced Decision:** APPROVED
**Approved Amount:** ₹4000.0
**Reasons:** 
**Adjustments:** Component failed gracefully.
**Confidence:** 0.7
**Trace (Verifier Output):**
```json
{
  "extracted_fields": {
    "Hospital Name": "Ayur Wellness Centre",
    "Line Items": "Panchakarma Therapy (5 sessions) 3000, Consultation 1000",
    "Subtotal": "4000",
    "Total Amount": "4000"
  },
  "trace_data": [
    {
      "agent": "Document Verifier (LLM)",
      "status": "SUCCESS",
      "output": {
        "document_type": "HOSPITAL_BILL",
        "key_fields": {
          "Hospital Name": "Ayur Wellness Centre",
          "Line Items": "Panchakarma Therapy (5 sessions) 3000, Consultation 1000",
          "Subtotal": "4000",
          "Total Amount": "4000"
        },
        "confidence": 1.0,
        "flags": [],
        "warnings": [],
        "detected_doc_types": [
          "PRESCRIPTION",
          "HOSPITAL_BILL"
        ],
        "required_doc_types": [
          "PRESCRIPTION",
          "HOSPITAL_BILL"
        ]
      },
      "duration_ms": 3083
    }
  ]
}
```

**Expected Outcome:** {
  "decision": "APPROVED",
  "system_must": [
    "Not crash or return a 500 error",
    "Indicate in the output that a component failed and was skipped",
    "Return a confidence score lower than a normal full-pipeline approval",
    "Include a note that manual review is recommended due to incomplete processing"
  ]
}
---

## TC012: Excluded Treatment
**Produced Decision:** REJECTED
**Approved Amount:** ₹2700.0
**Reasons:** PER_CLAIM_EXCEEDED: Claimed amount (8000.0) exceeds per-claim limit of 5000.0, LLM Flagged Line-Item Exclusion: Personalised Diet and Nutrition Program - Obesity and weight loss programs exclusion (-5000.0)
**Adjustments:** 
**Confidence:** 0.9
**Trace (Verifier Output):**
```json
{
  "extracted_fields": {
    "Line Items": "Bariatric Consultation 3000, Personalised Diet and Nutrition Program 5000",
    "Subtotal": "8000",
    "Total Amount": "8000"
  },
  "trace_data": [
    {
      "agent": "Document Verifier (LLM)",
      "status": "SUCCESS",
      "output": {
        "document_type": "HOSPITAL_BILL",
        "key_fields": {
          "Line Items": "Bariatric Consultation 3000, Personalised Diet and Nutrition Program 5000",
          "Subtotal": "8000",
          "Total Amount": "8000"
        },
        "confidence": 1.0,
        "flags": [],
        "warnings": [],
        "detected_doc_types": [
          "PRESCRIPTION",
          "HOSPITAL_BILL"
        ],
        "required_doc_types": [
          "PRESCRIPTION",
          "HOSPITAL_BILL"
        ]
      },
      "duration_ms": 3260
    }
  ]
}
```

**Expected Outcome:** {
  "decision": "REJECTED",
  "rejection_reasons": [
    "EXCLUDED_CONDITION"
  ],
  "confidence_score": "above 0.90"
}
---
