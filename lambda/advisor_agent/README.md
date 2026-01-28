# Advisor Agent (AWS Lambda)

This Lambda exposes an HTTP-friendly endpoint that n8n can call to generate:
- risk_score (0..1)
- explainable factors
- study recommendations

## n8n Usage
Use an HTTP Request node:
- Method: POST
- Body: JSON (avg_grade_pct, missing_14d, submitted_14d, days_inactive, etc.)
- Then send the returned recommendations via Email node.
