# Interview Prep Pack — Senior Product Analyst at NorthBank

## Likely questions
1. Walk me through an A/B test you designed end to end — how you set it up, what
   you measured, and what happened.
2. Tell me about a time your analysis changed a decision or a roadmap.
3. How do you decide which metrics matter for a product area you're new to?
4. Describe your SQL modelling approach for a messy, multi-source dataset.
5. You haven't used dbt — how would you get productive with it quickly?
6. Our domain is fintech and yours has been retail/marketing. How do you ramp on a
   new domain?
7. Tell me about mentoring another analyst. What did you actually change in how
   they worked?
8. How do you present a technical finding to a non-technical Product Manager?
9. A stakeholder disagrees with your test result and wants to ship anyway. What do
   you do?
10. What would your first 90 days as owner of a NorthBank product area look like?

## STAR answer scaffolds

### "Walk me through an A/B test you designed end to end."
- **Situation:** At BrightWave Retail, checkout conversion was a priority and the
  team wanted to test copy changes.
- **Task:** Design a trustworthy test and give a clear ship/don't-ship answer.
- **Action:** Designed the experiment, defined conversion as the primary metric,
  ran it, and interpreted the result.
- **Result:** An 8% conversion lift; the change was rolled out permanently. (All
  from your CV — keep the number exactly as stated.)

### "Tell me about a time your analysis changed a decision."
- **Situation / Task:** Use the same checkout-copy test, or the reporting rebuild
  that cut weekly reporting from ~6 hours to under 1.
- **Action:** Describe defining the metric, building the SQL/dashboard, and what
  the team did differently as a result.
- **Result:** Faster decisions / the permanent rollout. Stick to the real outcomes.

### "Describe your SQL modelling approach for messy data."
- **Situation:** Web, CRM and campaign data lived in a fragile spreadsheet process.
- **Task:** Make it reliable and reusable.
- **Action:** Modelled and joined the sources in SQL/PostgreSQL and Python (pandas).
- **Result:** Replaced the spreadsheet with a dependable pipeline. Honest note: you
  can add that dbt would be the natural next step for versioning these models.

### "Tell me about mentoring another analyst."
- **Situation:** A junior analyst joined the marketing team.
- **Task:** Raise the quality and independence of their work.
- **Action:** Reviewed their SQL and analytical approach weekly.
- **Result:** Be honest about scope — one analyst, steady improvement — and connect
  it to your appetite to raise the bar more widely at NorthBank.

### "How would you get productive with dbt quickly?" (honest-gap question)
- The CV has no dbt example, so don't invent one. Scaffold from the truth: your
  SQL modelling instincts, how you'd map your existing joins into dbt models and
  tests, and a concrete first-week learning plan. Say plainly you haven't used it yet.

## 5 smart questions to ask them
1. Which product area would this role own first — onboarding, payments, or savings —
   and what does "good" look like there in the next two quarters?
2. How does the Data team run experiments today, and where does the current process
   frustrate you most?
3. How mature is the dbt/modelling layer, and how much of this role is building it
   versus using it?
4. How do Product Managers and analysts actually make decisions together here — who
   owns the call when the data is ambiguous?
5. What does raising the analytical bar mean to you in practice — is it tooling,
   rigour, mentoring, or something else?
