"""
Strong causal/purpose markers for action dependency extraction.
Only high-confidence markers (LS >= 0.70) that indicate meaningful "leads to" relations.

Rules:
- Single-word inhibitory verbs (inhibits, blocks, prevents, suppresses) are NOT included
  as standalone markers — they appear too frequently as ordinary verbs in text and cause
  false positives. They are only valid when part of a phrase like "which inhibits" or
  "and thereby blocks".
"""

# Each entry: (pattern, link_score)
STRONG_MARKERS = [
    # Causal — highest confidence (phrase-level, unlikely to be a random verb)
    (r'\bleads?\s+to\b',                          0.90),
    (r'\bresults?\s+in\b',                        0.90),
    (r'\bcauses?\b',                              0.90),
    (r'\bproduces?\b',                            0.90),
    (r'\binduces?\b',                             0.90),
    # Logical consequence (connectives — safe, never appear as verbs)
    (r'\btherefore\b',                            0.85),
    (r'\bthus\b',                                 0.85),
    (r'\bhence\b',                                0.85),
    (r'\bconsequently\b',                         0.85),
    # Inhibitory in PHRASE form only (require preceding word to reduce false positives)
    (r'\bwhich\s+(?:prevents?|inhibits?|blocks?|suppresses?)\b',  0.85),
    (r'\bthereby\s+(?:preventing|inhibiting|blocking|suppressing)\b', 0.85),
    # Purpose
    (r'\bin\s+order\s+to\b',                      0.80),
    (r'\bso\s+that\b',                            0.80),
    (r'\bwith\s+the\s+aim\s+of\b',               0.80),
    (r'\bwith\s+the\s+goal\s+of\b',              0.80),
    # Enabling (phrase form only)
    (r'\bwhich\s+enables?\b',                     0.80),
    (r'\bthereby\s+\w+ing\b',                     0.80),   # "thereby activating"
    # Mechanism
    (r'\bby\s+means\s+of\b',                      0.75),
    (r'\bmediated\s+by\b',                        0.75),
    # NOTE: 'via' is intentionally excluded — it appears too frequently as a
    # prepositional phrase in biomedical text and produces false positives.
]
