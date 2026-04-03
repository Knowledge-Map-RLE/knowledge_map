"""Quick sanity check of updated should_confirm rules against known examples."""
import sys
sys.path.insert(0, "d:/Knowledge_Map/api")
from auto_review import should_confirm

tests = [
    # (src_phrase, tgt_phrase, relation, confidence, evidence, expected, label)

    # === Should be REJECTED (N from manual review) ===
    (
        "improve its future uptake across surgical units",
        "reduce the generalizability of the findings",
        "enables", 0.58, ["[obj_obj:surgical,units]"],
        False, "obj_obj:surgical,units — not concrete bio"
    ),
    (
        "promote emotional well-being cognitive engagement",
        "reducing fall risk",
        "enables", 0.58, ["[obj_obj:care]"],
        False, "obj_obj:care — abstract single token"
    ),
    (
        "improve functional outcomes",
        "enhance functional mobility in older patients",
        "enables", 0.58, ["[obj_obj:functional]"],
        False, "obj_obj:functional — abstract single token"
    ),
    (
        "accumulating damage",
        "generate that",
        "enables", 0.55, ["[subject:communities]"],
        False, "subject:communities — abstract"
    ),
    (
        "carry these biological imprints",
        "generate biological resilience",
        "enables", 0.58, ["[obj_obj:biological]"],
        False, "obj_obj:biological — abstract"
    ),
    (
        "replicate these patterns of temporal preparation",
        "replicate the findings of Study 1",
        "sequential", 0.75, ["Thus"],
        False, "meta-verb: replicate"
    ),
    (
        "reduce inappropriate vitamin D measurement",
        "reduced inappropriate vitamin D screenings",
        "enables", 0.58, ["[obj_obj:inappropriate,vitamin]"],
        False, "obj_obj:inappropriate,vitamin — no concrete bio token"
    ),
    (
        "influencing the quality of communication between caregivers",
        "acquired communication training and skills",
        "enables", 0.65, ["[keyword:caregivers]"],
        False, "keyword:caregivers — abstract/clinical"
    ),
    (
        "protect functional capacity",
        "maintain health and functional autonomy",
        "enables", 0.58, ["[obj_obj:functional]"],
        False, "obj_obj:functional — abstract"
    ),
    (
        "increasing the risk of adverse drug reactions",
        "cause cognitive decline",
        "enables", 0.58, ["[obj_obj:cognitive]"],
        False, "obj_obj:cognitive — abstract"
    ),
    (
        "facilitates the extraction of useful features",
        "enhancing the model's performance",
        "enables", 0.55, ["[subject:learning]"],
        False, "subject:learning — abstract/too short context"
    ),

    # === Should be CONFIRMED (P from manual review) ===
    (
        "increase the expression of antioxidant response genes",
        "attenuate oxidative stress-induced apoptotic signaling",
        "enables", 0.65, ["[keyword:antioxidant]"],
        True, "keyword:antioxidant — concrete bio"
    ),
    (
        "reduces ROS production and apoptosis",
        "increasing platelet yield",
        "causes", 0.82, ["thereby"],
        True, "marker:thereby + bio verbs"
    ),
    (
        "corrects aberrant placenta structure",
        "restoring fetal growth",
        "causes", 0.88, ["leading to"],
        True, "marker:leading to + bio verbs"
    ),
    (
        "promotes MERTK and TYRO3 induction",
        "maintaining homeostatic efferocytosis",
        "causes", 0.82, ["thereby"],
        True, "marker:thereby + bio verbs"
    ),
    (
        "medializes the glenohumeral center of rotation",
        "increasing the deltoid muscle's lever arm",
        "causes", 0.82, ["thereby"],
        True, "marker:thereby + bio verbs"
    ),
    (
        "upregulating AT1R expression",
        "promote Ang II production",
        "enables", 0.65, ["[keyword:at1r]"],
        True, "keyword:at1r — concrete molecule"
    ),
    (
        "phosphorylate tau at Ser202",
        "disrupts microtubule binding",
        "causes", 0.85, ["thereby"],
        True, "marker:thereby + phosphorylate (bio verb)"
    ),
    (
        "inhibiting PDE-4 including the activation of SIRT1",
        "activating FOXO and other transcription factors",
        "enables", 0.65, ["[keyword:sirt1]"],
        True, "keyword:sirt1 — concrete molecule"
    ),
    (
        "drive proplatelet formation",
        "impairs proplatelet formation",
        "enables", 0.65, ["[obj_obj:formation,proplatelet]"],
        True, "obj_obj:formation,proplatelet — proplatelet is concrete (conf>=0.65)"
    ),
    (
        "promote megakaryopoiesis",
        "maintaining redox hematopoiesis and megakaryopoiesis",
        "enables", 0.65, ["[obj_obj:megakaryopoiesis]"],
        True, "obj_obj:megakaryopoiesis — specific bio term (conf>=0.65)"
    ),

    # === New rules: HTML artifacts ===
    (
        "inhibit tau phosphorylation",
        "<td>Some protein function</td>",
        "enables", 0.65, ["[keyword:tau]"],
        False, "html artifact in tgt"
    ),
    (
        "<img src='http://example.com/fig1.jpg'>",
        "reduce neurodegeneration",
        "enables", 0.65, ["[keyword:neurodegeneration]"],
        False, "html artifact in src"
    ),

    # === New rules: tautological edges ===
    (
        "identify hospitalized frail older adults with frailty",
        "identify hospitalized frail older adults who benefit from intervention",
        "enables", 0.58, ["[obj_obj:adults,older]"],
        False, "tautological: identify frail adults ≈ identify frail adults"
    ),
    (
        "enhancing social connections among older adults",
        "enhancing interpersonal connections among older adults",
        "enables", 0.58, ["[obj_obj:connections]"],
        False, "tautological: enhancing connections ≈ enhancing connections"
    ),

    # === New abstract tokens: older, elderly, stress ===
    (
        "identify hospitalized older adults with frailty",
        "increases the vulnerability of older adults",
        "enables", 0.58, ["[obj_obj:adults,older]"],
        False, "obj_obj:adults,older — both abstract"
    ),
    (
        "increased their perceived stress",
        "increase healthcare personnel stress levels",
        "enables", 0.58, ["[obj_obj:stress]"],
        False, "obj_obj:stress — abstract"
    ),

    # === New rules: Cyrillic metadata leak ===
    (
        "**Авторы:** Su Qingqing, Liu Siqi",
        "identify resilience profiles in elderly patients",
        "enables", 0.58, ["[obj_obj:profiles,resilience]"],
        False, "cyrillic in src (author metadata)"
    ),

    # === New rules: tighter tautological (short phrase absolute overlap) ===
    (
        "detect fin whale 20 Hz calls from recordings",
        "detecting fin whale 20 Hz pulses in validation",
        "enables", 0.58, ["[obj_obj:whale]"],
        False, "tautological: detect fin whale (short phrase overlap)"
    ),

    # === New rule: [subject:] requires confidence >= 0.65 ===
    (
        "reduce their vocal activity during shooting",
        "reduced their calling rates during seismic survey",
        "enables", 0.55, ["[subject:whales]"],
        False, "subject:whales at conf=0.55 (below threshold)"
    ),
    # But [subject:] at conf 0.65 should still pass if bio verbs
    (
        "inhibiting PDE-4 including the activation of SIRT1",
        "activating FOXO and other transcription factors",
        "enables", 0.65, ["[keyword:sirt1]"],
        True, "keyword:sirt1 — concrete molecule (unchanged)"
    ),
    # === Bio-domain filter: non-bio articles with thereby ===
    (
        "reduces the effective contact area between asphalt and aggregate",
        "weakens adhesion performance",
        "sequential", 0.85, ["consequently"],
        False, "asphalt domain — no bio tokens"
    ),
    (
        "increases aging response rate and strength of the alloy",
        "produce an ingot using water-cooled copper mold",
        "enables", 0.65, ["[keyword:alloy]"],
        False, "alloy domain — no bio tokens"
    ),
    (
        "removing a complex learning activity to tick-box exercise",
        "shaping how students interpret purpose of research projects",
        "causes", 0.72, ["thereby"],
        False, "education domain — no bio tokens"
    ),
]

passed = 0
failed = 0
for src, tgt, rel, conf, evid, expected, label in tests:
    ok, reason = should_confirm(src, tgt, rel, conf, evid)
    status = "OK" if ok == expected else "FAIL"
    if ok == expected:
        passed += 1
    else:
        failed += 1
    mark = "  " if ok == expected else "!!"
    print(f"{mark} [{status}] expected={'P' if expected else 'N'} got={'P' if ok else 'N'} | {label}")
    if ok != expected:
        print(f"     reason: {reason}")

print(f"\nTotal: {passed}/{len(tests)} passed, {failed} failed")
