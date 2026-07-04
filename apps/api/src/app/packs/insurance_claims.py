"""Industry pack: insurance-claims (docs/03 §6).

A pack is data, not code: ontology vocabulary, alias maps for entity
resolution, pain-point cues mapped to a Lean-derived waste taxonomy, and
extraction hints. The extractors are generic; this file is where the
practitioner knowledge lives. Adding an industry later means authoring a
sibling module, not new engineering.
"""

# Canonical actors and their aliases (resolution merges aliases into the
# canonical name with high confidence).
ACTORS: dict[str, list[str]] = {
    "Intake Coordinator": ["intake coordinator", "intake coordinators"],
    "Intake Supervisor": ["intake supervisor"],
    "Claims Adjuster": ["adjuster", "adjusters", "field adjuster", "field adjusters",
                        "handling adjuster"],
    "Senior Adjuster": ["senior adjuster", "senior adjusters"],
    "Claims Supervisor": ["supervisor", "supervisors"],
    "Complex Claims Unit": ["complex claims unit", "complex claims", "complex adjuster"],
    "Special Investigations Unit": ["siu", "special investigations unit"],
    "Recovery Coordinator": ["recovery coordinator", "subrogation coordinator",
                             "recovery team"],
    "Claims Director": ["claims director"],
    "Compliance Team": ["compliance team"],
    "Accounts Payable": ["accounts payable", "accounts payable team"],
    "Call Center Agent": ["call center agent", "call center agents"],
    "Broker": ["broker", "brokers"],
}

# Known system-name patterns for this vertical: product-style CamelCase
# coinages plus explicit seeds.
SYSTEM_SEEDS: list[str] = [
    "ClaimCore", "CallTrak", "PolicyHub",
]
GENERIC_SYSTEM_TERMS: dict[str, str] = {
    "customer portal": "Customer Portal",
    "shared spreadsheet": "Shared Spreadsheet",
    "access database": "Access Database",
    "finance system": "Finance System",
}

# Pain-point cues → Lean waste taxonomy (docs/03 §3).
PAIN_CUES: list[tuple[str, str]] = [
    (r"re-?enter|re-?key|rekey|duplicate entry|enter(ed)? .{0,20}manually", "rework"),
    (r"manually|by hand|paper form|printed and keyed", "manual_work"),
    (r"wait|sat unassigned|delay|exceeds? the .{0,20}target|backlog", "waiting"),
    (r"lost|misses?|no (queue|tracking|structured field)|not report", "defects"),
    (r"email(ed)? to|by email|shared mailbox|emailed the", "handoff_friction"),
    (r"spreadsheet|access database|tracked in (a|the) (word|excel)", "shadow_it"),
    (r"transcription error|error rates?|wrong (vehicle|information)", "defects"),
]

# Business-rule cues: obligations, thresholds, time limits.
RULE_CUES = (
    r"\bmust\b|\brequires?\b|\bwithin \d+|\bno later than\b|"
    r"\bthreshold\b|\bapproved by\b|\bescalated? (to|when)\b"
)

# Step-type cues for process steps.
MANUAL_STEP_CUES = r"manually|re-?enter|print|paper|by hand|key(ed)? in|scan"
DECISION_STEP_CUES = r"\bif\b|\bwhen\b|\bdecid|\breview(s|ed)? (the|each)|\bapprov"

# Document classes worth mining for processes.
PROCESS_DOC_CLASSES = {"sop", "process_map", "policy"}
