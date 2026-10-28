TODO: replace with the Alessa triage rules from the approved SOPs.
Once the SOPs arrive they also go into Azure AI Search, and the agent retrieves the relevant sections per alert.

Placeholder rules so the pipeline runs end to end:
- Review every triggering transaction against the customer's normal activity (activity profile).
- If the activity is consistent with the customer's profile and history, recommend close with the reason.
- If the pattern is unexplained, involves high-risk countries, or repeats a prior reported pattern, recommend escalate.
- If data needed for the decision is missing, recommend needs_review and say what is missing.
