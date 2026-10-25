# United States insurance rules

These static resources summarize how the main United States insurance rules relate. They are decision context, not a coverage determination or legal advice. The controlling text is the current federal statute and the insurance code of the state where the policy is issued or the activity occurs.

Insurance in the United States is mostly state law. Federal statutes override that only when they specifically address insurance, or when they govern a federal program such as Medicare or the National Flood Insurance Program.

## How the rules relate

1. State insurance departments license insurers and producers, review rates and forms, and police unfair practices. See `decision-gate://rules/usa-insurance/state-regulation`.
2. Federal health statutes sit on top of that for health coverage: the Affordable Care Act, ERISA, COBRA, HIPAA, mental-health parity, the No Surprises Act, and GINA. Medicare and Medicaid are public programs with their own eligibility rules. See `decision-gate://rules/usa-insurance/health`.
3. Auto financial responsibility and workers' compensation are state commands. A standard homeowners policy is usually a contract requirement of a lender, not a statute. See `decision-gate://rules/usa-insurance/property-casualty`.
4. Flood is generally excluded from homeowners. A federal lender must require flood insurance on a building in a Special Flood Hazard Area. See `decision-gate://rules/usa-insurance/flood`.
5. Life, annuity, and long-term-care policy provisions are state insurance law, including free-look and contestability periods. See `decision-gate://rules/usa-insurance/life`.
6. Privacy cuts across lines. HIPAA covers health plans. The Gramm-Leach-Bliley Act and the Fair Credit Reporting Act cover insurers more broadly. See `decision-gate://rules/usa-insurance/privacy`.

## Using these in a decision

- Name the line of business, the state, and whether the coverage is an insurance policy or a self-funded employer plan.
- A self-funded ERISA plan is not treated as state insurance. An insured plan still has a state-regulated insurance contract.
- Do not treat a National Association of Insurance Commissioners model law as binding until that state has adopted it.
- Dollar limits, filing rules, and penalties change. Confirm them with the state insurance department or the current code before approving or rejecting on a numeric rule.
