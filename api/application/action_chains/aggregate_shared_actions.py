"""
Use case: агрегация Action-нод по лингвистической структуре.

Нормализация не зависит от порядка слов:
  norm_key = sha256(verb_canon + "|" + sorted(subject) + "|" + sorted(object_canon))[:16]

Синонимизация:
  Перед хешированием глаголы и ключевые объекты приводятся к каноническим формам,
  чтобы биологически идентичные действия из разных статей объединялись в один узел:
    suppress/block/prevent → inhibit
    mTORC1 → mTOR, autophagic flux → autophagy, TP53 → p53, etc.
"""
import hashlib

# ─── Словари синонимов ────────────────────────────────────────────────────────
#
# Ключи — lowercase. Используются до хеширования в compute_norm_key.
# Добавляйте новые синонимы по мере появления в корпусе.

# Глаголы: синонимичные действия → каноническая форма
VERB_SYNONYMS: dict[str, str] = {
    # Ингибирование / замедление
    "suppress":     "inhibit",
    "block":        "inhibit",
    "prevent":      "inhibit",
    "repress":      "inhibit",
    "attenuate":    "inhibit",
    "abrogate":     "inhibit",
    "abolish":      "inhibit",
    "impair":       "inhibit",
    "delay":        "inhibit",
    "slow":         "inhibit",
    "halt":         "inhibit",
    "arrest":       "inhibit",
    "blunt":        "inhibit",
    "dampen":       "inhibit",
    "silence":      "inhibit",
    "deplete":      "inhibit",
    "disrupt":      "inhibit",
    # Снижение уровня
    "decrease":     "reduce",
    "diminish":     "reduce",
    "downregulate": "reduce",
    "lower":        "reduce",
    "attenuate":    "reduce",
    "limit":        "reduce",
    # Активация / усиление
    "induce":       "activate",
    "trigger":      "activate",
    "stimulate":    "activate",
    "promote":      "activate",
    "enhance":      "activate",
    "upregulate":   "activate",
    "potentiate":   "activate",
    "facilitate":   "activate",
    "increase":     "activate",
    "boost":        "activate",
    "drive":        "activate",
    "accelerate":   "activate",
    "amplify":      "activate",
    "augment":      "activate",
    "restore":      "activate",
    "cause":        "activate",   # cause apoptosis ≈ induce apoptosis
    "generate":     "activate",   # generate ROS ≈ increase ROS (производство = активация процесса)
    "prolong":      "activate",   # prolong lifespan ≈ extend lifespan
    "extend":       "activate",   # extend lifespan
    # Регуляция (без направления)
    "regulate":     "modulate",
    "control":      "modulate",
    "govern":       "modulate",
    "coordinate":   "modulate",
    "modulate":     "modulate",
    # Экспрессия / продукция
    "express":      "produce",
    "secrete":      "produce",
    "release":      "produce",
    # "generate" → activate (defined above in activation group — generate ROS ≈ increase ROS)
    "synthesize":   "produce",
    "transcribe":   "produce",
    "translate":    "produce",
    # Связывание
    "bind":         "interact",
    "interact":     "interact",
    "associate":    "interact",
    "complex":      "interact",
}

# Объекты/сущности: синонимичные термины → каноническое имя
ENTITY_SYNONYMS: dict[str, str] = {
    # ── Долголетие ────────────────────────────────────────────────────────────
    "healthspan":                       "longevity",
    "lifespan":                         "longevity",
    "life expectancy":                  "longevity",
    "life span":                        "longevity",
    "maximum lifespan":                 "longevity",
    "longevity":                        "longevity",
    # ── Старение ──────────────────────────────────────────────────────────────
    "aging process":                    "aging",
    "ageing":                           "aging",
    "age-related":                      "aging",
    "biological aging":                 "aging",
    "organismal aging":                 "aging",
    # ── Сенесценция ───────────────────────────────────────────────────────────
    "cellular senescence":              "senescence",
    "replicative senescence":           "senescence",
    "stress-induced senescence":        "senescence",
    "oncogene-induced senescence":      "senescence",
    "therapy-induced senescence":       "senescence",
    # ── mTOR ──────────────────────────────────────────────────────────────────
    "mtorc1":                           "mtor",
    "mtorc2":                           "mtor",
    "mammalian target of rapamycin":    "mtor",
    "mechanistic target of rapamycin":  "mtor",
    "mtor complex 1":                   "mtor",
    "mtor complex 2":                   "mtor",
    "mtor pathway":                     "mtor",
    "mtor signaling":                   "mtor",
    # ── AMPK ──────────────────────────────────────────────────────────────────
    "amp-activated protein kinase":     "ampk",
    "amp kinase":                       "ampk",
    "ampk pathway":                     "ampk",
    "ampk signaling":                   "ampk",
    # ── Сиртуины ──────────────────────────────────────────────────────────────
    "sirt1":                            "sirtuin",
    "sirt2":                            "sirtuin",
    "sirt3":                            "sirtuin",
    "sirt6":                            "sirtuin",
    "sirt7":                            "sirtuin",
    "sir2":                             "sirtuin",
    "sirtuin 1":                        "sirtuin",
    "sirtuin-1":                        "sirtuin",
    "sirtuins":                         "sirtuin",
    "sirtuin activity":                 "sirtuin",
    "sirtuin expression":               "sirtuin",
    "sirtuin signaling":                "sirtuin",
    # ── NAD ───────────────────────────────────────────────────────────────────
    "nad+":                             "nad",
    "nad":                              "nad",
    "nicotinamide adenine dinucleotide": "nad",
    "nicotinamide riboside":            "nad",
    "nmn":                              "nad",
    "nicotinamide mononucleotide":      "nad",
    # ── Аутофагия ─────────────────────────────────────────────────────────────
    "autophagic flux":                  "autophagy",
    "macroautophagy":                   "autophagy",
    "autophagy induction":              "autophagy",
    "autophagic degradation":           "autophagy",
    "autophagosome":                    "autophagy",
    "mitophagy":                        "autophagy",
    "selective autophagy":              "autophagy",
    "beclin-1":                         "autophagy",
    "beclin 1":                         "autophagy",
    "lc3":                              "autophagy",
    "lc3-ii":                           "autophagy",
    "atg":                              "autophagy",
    # ── p53 ───────────────────────────────────────────────────────────────────
    "tp53":                             "p53",
    "tumor protein p53":                "p53",
    "tumor suppressor p53":             "p53",
    "p53 pathway":                      "p53",
    "p53 signaling":                    "p53",
    # ── p21 ───────────────────────────────────────────────────────────────────
    "cdkn1a":                           "p21",
    "cip1":                             "p21",
    "waf1":                             "p21",
    "p21cip1":                          "p21",
    # ── ROS ───────────────────────────────────────────────────────────────────
    "reactive oxygen species":          "ros",
    "reactive oxygen":                  "ros",
    "superoxide":                       "ros",
    "hydrogen peroxide":                "ros",
    "oxidative stress":                 "ros",
    "free radicals":                    "ros",
    "oxidative damage":                 "ros",
    # ── Воспаление ────────────────────────────────────────────────────────────
    "inflammatory response":            "inflammation",
    "neuroinflammation":                "inflammation",
    "systemic inflammation":            "inflammation",
    "chronic inflammation":             "inflammation",
    "inflammaging":                     "inflammation",
    "inflammatory signaling":           "inflammation",
    # ── NF-kB ─────────────────────────────────────────────────────────────────
    "nf-kb":                            "nf-kb",
    "nfkb":                             "nf-kb",
    "nuclear factor kappa b":           "nf-kb",
    "nuclear factor-kb":                "nf-kb",
    "nf-kappab":                        "nf-kb",
    # ── Апоптоз ───────────────────────────────────────────────────────────────
    "cell death":                       "apoptosis",
    "programmed cell death":            "apoptosis",
    "caspase activation":               "apoptosis",
    "apoptotic cell death":             "apoptosis",
    # ── Клеточный цикл ────────────────────────────────────────────────────────
    "cell cycle arrest":                "cell cycle",
    "cell cycle progression":           "cell cycle",
    "cell cycle inhibition":            "cell cycle",
    "cell cycle checkpoint":            "cell cycle",
    # ── ДНК-повреждения / репарация ───────────────────────────────────────────
    "dna damage":                       "dna repair",
    "dna double strand break":          "dna repair",
    "dna double-strand break":          "dna repair",
    "dna damage response":              "dna repair",
    "dna repair pathway":               "dna repair",
    "genomic instability":              "dna repair",
    # ── Теломеры ──────────────────────────────────────────────────────────────
    "telomere length":                  "telomere",
    "telomere shortening":              "telomere",
    "telomere attrition":               "telomere",
    "telomere erosion":                 "telomere",
    "telomerase activity":              "telomere",
    # ── SASP ──────────────────────────────────────────────────────────────────
    "senescence-associated secretory phenotype": "sasp",
    "sasp factors":                     "sasp",
    "sasp components":                  "sasp",
    "senescence-associated inflammation": "sasp",
    # ── Митохондрии ───────────────────────────────────────────────────────────
    "mitochondrial function":           "mitochondria",
    "mitochondrial dysfunction":        "mitochondria",
    "mitochondrial membrane":           "mitochondria",
    "mitochondrial biogenesis":         "mitochondria",
    "mitochondrial membrane potential": "mitochondria",
    "mitochondrial fission":            "mitochondria",
    "mitochondrial fusion":             "mitochondria",
    "mitochondrial respiration":        "mitochondria",
    # ── Инсулин / IGF-1 ───────────────────────────────────────────────────────
    "igf-1":                            "insulin-igf1",
    "igf1":                             "insulin-igf1",
    "insulin-like growth factor":       "insulin-igf1",
    "insulin signaling":                "insulin-igf1",
    "igf-1 signaling":                  "insulin-igf1",
    "igf-1r":                           "insulin-igf1",
    # ── Эпигенетика ───────────────────────────────────────────────────────────
    "epigenetic modification":          "epigenetics",
    "epigenetic regulation":            "epigenetics",
    "epigenetic clock":                 "epigenetics",
    "dna methylation":                  "epigenetics",
    "histone modification":             "epigenetics",
    "chromatin remodeling":             "epigenetics",
    # ── Протеостаз / убиквитин ────────────────────────────────────────────────
    "proteasome activity":              "proteostasis",
    "ubiquitin-proteasome":             "proteostasis",
    "protein aggregation":              "proteostasis",
    "protein homeostasis":              "proteostasis",
    "unfolded protein response":        "proteostasis",
    "heat shock protein":               "proteostasis",
}


def _canon_verb(verb: str) -> str:
    """Приводит глагол к канонической форме через VERB_SYNONYMS."""
    v = verb.lower().strip()
    return VERB_SYNONYMS.get(v, v)


def _canon_entity(text: str) -> str:
    """Приводит название сущности к канонической форме через ENTITY_SYNONYMS."""
    t = text.lower().strip()
    # Сначала точное совпадение всей фразы
    if t in ENTITY_SYNONYMS:
        return ENTITY_SYNONYMS[t]
    # Затем проверяем, содержит ли фраза синоним как подстроку
    for synonym, canonical in ENTITY_SYNONYMS.items():
        if synonym in t:
            return canonical
    return t


def compute_norm_key(verb: str, subject: str | None, obj: str | None,
                     verb_span: dict | None = None,
                     subject_span: dict | None = None,
                     object_span: dict | None = None) -> str:
    """
    Вычисляет детерминированный ключ нормализации для Action-ноды.

    Поддерживает два режима:
    1. Legacy: строковые verb/subject/obj (для обратной совместимости)
    2. Новый: span-словари с полной лингвистической структурой

    Шаги:
    1. Глагол → каноническая форма (VERB_SYNONYMS)
    2. subject и object → канонические формы (ENTITY_SYNONYMS)
    3. Токены каждого поля сортируются (инвариант к порядку слов)
    4. SHA-256[:16] итогового ключа

    Возвращает 16-символьный hex-дайджест SHA-256.
    """
    def norm(t: str | None) -> str:
        if not t:
            return ""
        canonical = _canon_entity(t)
        return " ".join(sorted(canonical.lower().strip().split()))

    # Если есть span-данные — используем их для более точной нормализации
    if verb_span:
        canon_verb = _canon_verb(verb_span.get("lemma_form", verb))
    else:
        canon_verb = _canon_verb(verb)

    if subject_span:
        subj_text = subject_span.get("lemma_form", subject or "")
    else:
        subj_text = subject or ""

    if object_span:
        obj_text = object_span.get("lemma_form", obj or "")
    else:
        obj_text = obj or ""

    key = f"{canon_verb}|{norm(subj_text)}|{norm(obj_text)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
