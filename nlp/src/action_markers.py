"""
Strong causal/purpose markers for action dependency extraction.
Only high-confidence markers (LS >= 0.70) that indicate meaningful "leads to" relations.
"""

# Each entry: (pattern, link_score)
STRONG_MARKERS = [
    # Causal — highest confidence
    (r'\bleads?\s+to\b',                          0.90),
    (r'\bresults?\s+in\b',                        0.90),
    (r'\bcauses?\b',                              0.90),
    (r'\bproduces?\b',                            0.90),
    (r'\binduces?\b',                             0.90),
    # Logical consequence
    (r'\btherefore\b',                            0.85),
    (r'\bthus\b',                                 0.85),
    (r'\bhence\b',                                0.85),
    (r'\bconsequently\b',                         0.85),
    # Inhibitory — also "leads to" semantically
    (r'\bprevents?\b',                            0.85),
    (r'\binhibits?\b',                            0.85),
    (r'\bblocks?\b',                              0.85),
    (r'\bsuppresses?\b',                          0.85),
    # Purpose
    (r'\bin\s+order\s+to\b',                      0.80),
    (r'\bso\s+that\b',                            0.80),
    (r'\bwith\s+the\s+aim\s+of\b',               0.80),
    (r'\bwith\s+the\s+goal\s+of\b',              0.80),
    # Enabling (только специфичные формы)
    (r'\bwhich\s+enables?\b',                     0.80),
    (r'\bthereby\s+\w+ing\b',                     0.80),  # "thereby activating" — конкретнее
    # Mechanism (только специфичные)
    (r'\bby\s+means\s+of\b',                      0.75),
    (r'\bmediated\s+by\b',                        0.75),
]
