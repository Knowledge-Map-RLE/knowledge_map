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
    # Additional causal verbs relevant for cancer/PD articles
    (r'\bdrives?\b',                              0.88),
    (r'\bpromotes?\b',                            0.85),
    (r'\bactivates?\b',                           0.85),
    (r'\bphosphorylates?\b',                      0.88),
    (r'\bdegrades?\b',                            0.82),
    (r'\bstabilizes?\b',                          0.80),
    (r'\bwhich\s+(?:activates?|triggers?|initiates?)\b',       0.82),
    (r'\bwhich\s+(?:degrades?|disrupts?|impairs?|damages?)\b', 0.82),
    # Logical consequence (connectives — safe, never appear as verbs)
    (r'\btherefore\b',                            0.85),
    (r'\bthus\b',                                 0.85),
    (r'\bhence\b',                                0.85),
    (r'\bconsequently\b',                         0.85),
    # Causal connective (sentence-level)
    (r'\bbecause\b',                              0.82),
    # Participial causal forms
    (r'\bleading\s+(?:either\s+)?to\b',           0.88),  # "leading to", "leading either to"
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
    (r'\bthereby\b',                              0.82),   # "thereby trigger", "thereby activate", etc.
    # Mechanism
    (r'\bby\s+means\s+of\b',                      0.75),
    (r'\bmediated\s+by\b',                        0.75),
    # NOTE: 'via' is intentionally excluded — it appears too frequently as a
    # prepositional phrase in biomedical text and produces false positives.
]

# Maps each pattern string → relation_subtype string
# Used by _classify_subtype() in action_extractor.py
MARKER_SUBTYPE_MAP: dict[str, str] = {
    r'\bleads?\s+to\b':           'causes',
    r'\bresults?\s+in\b':         'causes',
    r'\bcauses?\b':               'causes',
    r'\bproduces?\b':             'causes',
    r'\binduces?\b':              'causes',
    r'\bdrives?\b':               'causes',
    r'\bpromotes?\b':             'causes',
    r'\bactivates?\b':            'causes',
    r'\bphosphorylates?\b':       'via_mechanism',
    r'\bdegrades?\b':             'causes',
    r'\bstabilizes?\b':           'via_mechanism',
    r'\bwhich\s+(?:activates?|triggers?|initiates?)\b':       'causes',
    r'\bwhich\s+(?:degrades?|disrupts?|impairs?|damages?)\b': 'causes',
    r'\btherefore\b':             'sequential',
    r'\bthus\b':                  'sequential',
    r'\bhence\b':                 'sequential',
    r'\bconsequently\b':          'sequential',
    r'\bwhich\s+(?:prevents?|inhibits?|blocks?|suppresses?)\b': 'prevents',
    r'\bthereby\s+(?:preventing|inhibiting|blocking|suppressing)\b': 'prevents',
    r'\bbecause\b':               'causes',
    r'\bleading\s+(?:either\s+)?to\b': 'causes',
    r'\bin\s+order\s+to\b':       'enables',
    r'\bso\s+that\b':             'enables',
    r'\bwith\s+the\s+aim\s+of\b': 'enables',
    r'\bwith\s+the\s+goal\s+of\b': 'enables',
    r'\bwhich\s+enables?\b':      'enables',
    r'\bthereby\b':               'causes',
    r'\bby\s+means\s+of\b':       'via_mechanism',
    r'\bmediated\s+by\b':         'via_mechanism',
}
