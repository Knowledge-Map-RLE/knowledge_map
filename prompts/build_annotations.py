import re, sys, io

sys.stdout.reconfigure(encoding='utf-8')

with open('Новый формат статьи. Второй этап.eng.md', 'r', encoding='utf-8') as f:
    content = f.read()

first = content.index('---')
second = content.index('---', first + 3)
yaml_end = second + 3
text_start = content.index('#', yaml_end)
article = content[text_start:]

def find(text, start=0):
    idx = article.find(text, start)
    if idx == -1:
        raise ValueError(f'NOT FOUND from {start}: {repr(text[:80])}')
    return idx, idx + len(text)

# ============================================================
# GOALS (50 total: 3 success, 47 failure)
# ============================================================

goals_raw = [
    ("In this minireview, we explore the complexity of PD and propose a systems-based approach, organizing the available information around cellular disease hallmarks.", "Успешная цель", 0.88),
    ("We encourage our peers to adopt this cell-based view with the aim of improving communication in interdisciplinary research endeavors targeting the molecular events, modulatory cell-to-cell signaling pathways and emerging clinical phenotypes related to PD.", "Успешная цель", 0.80),
    ("It is tempting to speculate that the search for the origin and effective treatment of this disease will continue to add complexity to the scientific literature.", "Не успешная цель", 0.72),
    ("However, appreciating the progress in cancer research [6] [7], we anticipate otherwise: the new generation of PD researchers will be practicing a dramatically different type of science than PD researchers from the old school, which deserves full credit for developments such as dopamine substitution and deep brain stimulation.", "Не успешная цель", 0.70),
    ("The complex relationships between molecular, cellular and clinical traits will need to be explained in an intelligible way, in terms of a small number of underlying principles.", "Не успешная цель", 0.85),
    ("In this review, we focus on the cellular hallmarks of PD, and discuss strategies for understanding the relationships between these cellular traits, molecular factors, and clinical traits.", "Успешная цель", 0.90),
    ("However, many of those have been identified only on the basis of chromosomal linkage studies and causality, and confirmation is still pending.", "Не успешная цель", 0.82),
    ("Incomplete penetrance, variable expression and phenocopies often pose problems in assessing whether PD is caused solely by genetic susceptibility or is modified by environmental factors.", "Не успешная цель", 0.78),
    ("The exact role of environmental factors in the pathogenesis of PD remains elusive.", "Не успешная цель", 0.88),
    ("In contrast, the chronology and mechanisms of cell type-specific and PD subtype-specific cellular dysfunction remain to be elucidated.", "Не успешная цель", 0.90),
    ("Although PD pathogenesis has been associated with different cellular dysfunctions, it is likely that the respective initial tipping point of disease progression is caused by a PD subtypespecific process.", "Не успешная цель", 0.68),
    ("Finally, it is also likely that multiple hits on different cellular targets may hasten the emergence of higher-scale organic dysfunction.", "Не успешная цель", 0.65),
    ("This hypothesis states that PD could have its origin in the bulbus olfactorius, in the motor nucleus of the vagal nerve, or at a strictly peripheral site.", "Не успешная цель", 0.72),
    ("However, it remains to be seen whether this ascending spread of the disease is related to a-synuclein or other factors.", "Не успешная цель", 0.90),
    ("Despite all the progress made in understanding mitochondrial biology and its role in controlling apoptosis, it is not well understood why mitochondrial dysfunction takes such a center stage in PD [55] [56].", "Не успешная цель", 0.90),
    ("It has been speculated that these physiological cellular characteristics could potentially explain the selective local degeneration of both DA and non-DA cells in PD [60] [61].", "Не успешная цель", 0.70),
    ("It is likely that many of these processes are directly or indirectly involved in PD pathogenesis, even though it is not clear whether they are causative or consequential.", "Не успешная цель", 0.72),
    ("Thus far, these efforts have not yielded clear answers, but it has been observed that neurons of patients with PD have an unusually high rate of mitochondrial DNA deletions [74].", "Не успешная цель", 0.92),
    ("Their precise mechanisms of action remain to be understood.", "Не успешная цель", 0.90),
    ("Potential chelation therapies are currently under development [89].", "Не успешная цель", 0.80),
    ("It is likely that the high number and the widespread distribution of synapses, with the accompanying high local demands on energy and $Ca^{2+}$ buffering resources, correlate with decreased robustness of SN DA neurons against mitochondrial dysfunction and axonal transport defects [54].", "Не успешная цель", 0.68),
    ("Neither the complex etiology of PD nor its relationship with neuroinflammation are yet fully understood (Fig. 2).", "Не успешная цель", 0.90),
    ("It remains unclear, however, whether neuroinflammation is purely a side effect of PD, or whether it plays a more causal role in the pathogenesis.", "Не успешная цель", 0.90),
    ("Given this plethora of supporting evidence, we believe that neuroinflammation is at least a modulator of disease progression, and that further basic research in this field is needed to form the basis for future developments that target inflammatory pathways for disease-modifying therapies [109].", "Не успешная цель", 0.78),
    ("Looking forward, we believe that important new developments will come from more holistic, systems-based approaches that aim to understand the transfer functions between molecular, cellular, intercellular and high-level pathogenic events.", "Не успешная цель", 0.72),
    ("Finally, we stress that the heterogeneous disease progression observed from patient to patient cannot be understood with oversimplified reductionist views.", "Не успешная цель", 0.85),
    ("The challenge is to understand the key factors in each case, and to bring this concept to the level of personalized medicine.", "Не успешная цель", 0.88),
    ("In turn, increased efforts are required to coordinate and integrate interdisciplinary PD research.", "Не успешная цель", 0.82),
    ("The ultimate aim in systems PD biomedicine is to translate mechanistic insights into clinical applications, and to use these to improve patient quality of life [110].", "Не успешная цель", 0.85),
    ("One important challenge is the need to develop theoretical models that are able to accurately represent the pathogenesis of PD.", "Не успешная цель", 0.88),
    ("We believe that such models will help interdisciplinary cooperation by helping to structure both the interdisciplinary learning process and the formulation of testable key hypotheses.", "Не успешная цель", 0.70),
    ("However, a multifactorial disease such as PD, whose progression is believed to be influenced by the collective action of several genes and environmental factors, cannot be adequately represented by a simple model.", "Не успешная цель", 0.85),
    ("The multifactorial nature renders making predictions related to onset and progression a very challenging task.", "Не успешная цель", 0.85),
    ("Adequate multiple-scale models, aiming to bring PD research to a more integrated level, should therefore aim to understand the subsystem properties that connect the scales and to incorporate information about as many manageable factors as possible, including environmental factors, genetics, proteomics, metabolomics, cell biology, higher-level physiology, and patient quality of life.", "Не успешная цель", 0.78),
    ("The main challenge will be to understand the transfer functions that connect the multiple scales involved in PD pathogenesis.", "Не успешная цель", 0.88),
    ("We believe that our understanding of the signaling pathways connecting molecular events to clinical traits will have made significant progress in a decade from now.", "Не успешная цель", 0.68),
    ("In addition to an appropriate analytical framework, it will be crucial to develop noninvasive experimental approaches for time-resolved analyses in experimental models.", "Не успешная цель", 0.85),
    ("Because of the multitude of relevant cellular phenotypes in PD, and the need to understand causality in cellular pathogenesis, we believe that light microscopy applications in systems biology will be a major source of data in time-resolved multifactorial single-cell analysis [118].", "Не успешная цель", 0.68),
    ("We also think that the integration of information from different, coordinated experimental approaches, combined with appropriate modeling strategies, will greatly enhance our understanding of PD pathogenesis, as well as the predictive power for early PD diagnosis and personalized identification of underlying disease factors.", "Не успешная цель", 0.68),
    ("Currently, genetic testing of patients with PD is already possible, and is acting as a driving force for translational research; the current lack of PD subtypespecific therapies, however, makes the use of such genetic testing disputable [12] [119].", "Не успешная цель", 0.80),
    ("Preparing for an integrated systems-level understanding of PD is now within reach, but remains an extremely ambitious goal.", "Не успешная цель", 0.88),
    ("We believe that this major endeavor will pave the way for a new era of improved personalized medicine.", "Не успешная цель", 0.65),
    ("More short-term goals include improved human cell culture models for genetic and pharmacological screening approaches, and the development of more efficient differentiation methods for patient-derived induced pluripotent stem cells [120], as well as improved animal models for translational research [98].", "Не успешная цель", 0.78),
    ("In ongoing projects, the integration of high-dimensional and nonlinear data is already creating an interesting challenge for data interpretation, and stresses the urgent need to extend the application of systems theory to PD research.", "Не успешная цель", 0.82),
    ("Although regenerative medicine aiming to restore dopamine levels in the striatum offers transient relief from at least some clinical symptoms, we believe that systems approaches will allow for the development of increasingly sustainable and personalized disease-modifying therapies.", "Не успешная цель", 0.72),
    ("However, causative treatment approaches for PD have not yet become available, and both motor and nonmotor symptoms continue to interfere with patient quality of life.", "Не успешная цель", 0.95),
    ("This fact highlights the complexity of this disease, and stresses the need for an intelligible integration of findings from 200 years of PD research.", "Не успешная цель", 0.82),
    ("There are two main take-home messages [6] [7]: first, it is crucial to define the signals exchanged between various cell types involved in the disease, and it is important to understand the effects of those signals on the integrated circuits of each of those cell types.", "Не успешная цель", 0.85),
    ("Second, to develop accurate disease prognosis and treatment paradigms, it will be crucial to reach a level of mathematical clarity with regard to pathogenesis mechanisms, integrating the conceptual structure of systems theory and the logical coherence of neuroscience.", "Не успешная цель", 0.85),
    ("We foresee that PD research will evolve to be an increasingly exact science, in which the growing myriad of measurable phenotypic traits will be understood as manifestations of a small set of key principles.", "Не успешная цель", 0.70),
]

goals = []
goal_offsets = {}  # start_offset -> uid
for i, (text, atype, conf) in enumerate(goals_raw):
    uid = f'g{i+1}'
    start, end = find(text)
    color = '#4CAF50' if atype == 'Успешная цель' else '#F44336'
    goals.append((uid, text, atype, start, end, color, conf))
    goal_offsets[start] = uid

print(f'Goals: {len(goals)} (success: {sum(1 for g in goals if g[2]=="Успешная цель")}, failure: {sum(1 for g in goals if g[2]=="Не успешная цель")})')

# ============================================================
# SPANS - each text must be unique AND not overlap with any goal
# ============================================================

spans_raw = [
    # s1: Fig.1 caption - paper delivered on hallmarks promise
    ("Correlations between the represented cellular phenotypes and disease progression are well established.",
     "Фрагмент ведёт к успеху", 0.80),
    # s2: Abstract - rich body of knowledge
    ("Since the discovery of dopamine as a neurotransmitter in the 1950s, Parkinson's disease (PD) research has generated a rich and complex body of knowledge, revealing PD to be an age-related multifactorial disease, influenced by both genetic and environmental factors.",
     "Фрагмент ведёт к успеху", 0.80),
    # s3: Abstract - nonlinear complexity
    ("The tremendous complexity of the disease is increased by a nonlinear progression of the pathogenesis between molecular, cellular and organic systems.",
     "Фрагмент ведёт к неуспеху", 0.82),
    # s4: Intro - pragmatic approaches
    ("The approaches that have driven the development of these treatments have been practice-oriented and often pragmatic.",
     "Фрагмент ведёт к неуспеху", 0.70),
    # s5: Intro - conceptual change needed
    ("The fundamental conceptual change required to progress efficiently from this point will be to develop PD research into a more exact science in terms of mathematical concepts.",
     "Фрагмент ведёт к неуспеху", 0.78),
    # s6: Genetic - Mendelian forms context
    ("In 5-10% of cases, PD presents as a Mendelian form with autosomal dominant or recessive inheritance.",
     "Фрагмент ведёт к неуспеху", 0.65),
    # s7: Environmental - linked to rural life
    ("PD has also been linked to living in a rural environment, gardening, farming, and occupational exposure to agricultural chemicals [25].",
     "Фрагмент ведёт к неуспеху", 0.70),
    # s8: Environmental - correlations established
    ("However, it is well established that both environmental and genetic factors correlate with cellular phenotypes that can be considered to be cellular hallmarks of PD (Fig. 1).",
     "Фрагмент ведёт к неуспеху", 0.72),
    # s9: Synuclein - Braak spreading via gut
    ("One idea is that the spread of PD pathogenesis may start in the gastrointestinal tract and propagate cell to cell, spreading from the enteric nervous system all the way up to the brainstem, midbrain, and other parts of the central nervous system (CNS), finally resulting in disease staging, as proposed by Braak et al. [30].",
     "Фрагмент ведёт к неуспеху", 0.75),
    # s10: Mito - DA neuron anatomy
    ("DA neurons have extremely long projections from the SN into the striatum, are unmyelinated, and are characterized by a high degree of arborization and a high number of synapses [57] [58].",
     "Фрагмент ведёт к неуспеху", 0.75),
    # s11: Mito - at-risk neuron features
    ("Interestingly, the at-risk populations of neurons share a number of features with DA neurons, including highly branched axons, pacemaker activity, elevated oxidative stress, and $Ca^{2+}$ buffering stress.",
     "Фрагмент ведёт к неуспеху", 0.72),
    # s12: Mito - roles beyond energy
    ("In addition to their pivotal roles in energy metabolism and $Ca^{2+}$ homeostasis, mitochondria are important in many other processes, such as programmed cell death and inflammatory reactions [55].",
     "Фрагмент ведёт к неуспеху", 0.72),
    # s13: Mito - heteroplasmy challenge
    ("One of the biggest challenges in the analysis of mitochondrial DNA mutations is heteroplasmy-the fact that each individual cell can contain hundreds of mitochondria, and not all of them will carry the same mutation.",
     "Фрагмент ведёт к неуспеху", 0.82),
    # s14: Iron - PLA2G6/ATP13A2 correlation
    ("Two genetic PD factors that are clearly correlated with iron accumulation are PLA2G6 and ATP13A2 [85] [86].",
     "Фрагмент ведёт к неуспеху", 0.70),
    # s15: Iron - multiple metals involved
    ("Inter- estingly, not only iron but also other redox metals, such as copper, and nonredox metals, such as zinc, have also been reported to be involved in oxidative stress in the context of age-related neurodegenerative diseases [88].",
     "Фрагмент ведёт к неуспеху", 0.68),
    # s16: Synaptic - 150K terminals per neuron
    ("SN DA neurons have a very complex morphology, with ~ 150 000 presynaptic terminals per neuron in the striatum [90].",
     "Фрагмент ведёт к неуспеху", 0.70),
    # s17: Neuro - secondary detrimental effect
    ("In the majority of experimental approaches, neuroinflammation is a secondary detrimental effect triggered by PD-related chemical or genetic stress factors [98].",
     "Фрагмент ведёт к неуспеху", 0.75),
    # s18: Neuro - microglia/astrocyte imbalance
    ("The high number of microglia promoting neuroinflammation, opposing a low number of regulatory astrocytes, appears to provide a plausible explanation for the elevated risk of neuroinflammation in this brain region.",
     "Фрагмент ведёт к неуспеху", 0.72),
    # s19: Neuro - microglia detect synuclein
    ("For example, microglia are able to detect misfolded a-synuclein and increase neurotoxicity through the production of ROS and proinflammatory cytokines [99] [100].",
     "Фрагмент ведёт к неуспеху", 0.70),
    # s20: Fig2 - nonlinear motor symptom onset
    ("It is important to understand that the onset of motor symptoms does not correlate in a linear manner with the decrease in the number of DA neurons.",
     "Фрагмент ведёт к неуспеху", 0.78),
    # s21: Fig1 - shared phenotypes across subtypes
    ("All subtypes of PD may share common cellular phenotypes.",
     "Фрагмент ведёт к неуспеху", 0.62),
    # s22: Systems - spatiotemporal information flow
    ("The progression of the syndrome emerges from the flow of spatiotemporal information between molecular and organic scales.",
     "Фрагмент ведёт к неуспеху", 0.75),
    # s23: Systems - added layers of complexity
    ("However, neuroscience research based on molecular and cellular biology has added further layers of complexity to our understanding of PD.",
     "Фрагмент ведёт к неуспеху", 0.72),
    # s24: Intro - symptomatic treatment only
    ("Treatment of PD is currently symptomatic, and essentially involves substituting dopamine, or suppressing pathological neuronal oscillations via deep brain stimulation.",
     "Фрагмент ведёт к неуспеху", 0.91),
    # s25: Concluding - 200 years, still only symptomatic
    ("Two centuries after the first detailed clinical description of PD by James Parkinson, and more than a decade after the first identification of genetic factors in this disease, PD research has evolved into a very mature research field, which has developed an arsenal of successfully applied symptomatic treatments.",
     "Фрагмент ведёт к неуспеху", 0.78),
    # s26: Systems - phenotypic buffering challenge
    ("A major challenge in the experimental analysis of multifactorial diseases is the extensive phenotypic buffering driven by network robustness.",
     "Фрагмент ведёт к неуспеху", 0.75),
    # s27: Systems - Wellstead systems-control approach
    ("Wellstead et al. recently described a systems-control approach in which disturbances in energy metabolism act as a driving core module, and serve as an analytical and modeling framework with which to study the pathogenesis of PD [112] [113].",
     "Фрагмент ведёт к неуспеху", 0.70),
    # s28: Systems - graphical network modeling
    ("Graphical network modeling can provide an adequate view of a dynamic system such as PD, which is defined by the coordinated action of several factors and their local dynamics [111].",
     "Фрагмент ведёт к неуспеху", 0.65),
    # s29: Systems - prerequisites for understanding
    ("Detailed knowledge of both biology and systems theory are prerequisites for meaningfully furthering our understanding of PD.",
     "Фрагмент ведёт к неуспеху", 0.72),
    # s30: Concluding - only a few fields more advanced
    ("Only a few research fields in translational medicine are more advanced than PD research and hence can serve as role models.",
     "Фрагмент ведёт к неуспеху", 0.68),
    # s31: Systems - energy metabolism integration
    ("It is important to keep in mind that energy metabolism is highly integrated with complex cell-to-cell interactions.",
     "Фрагмент ведёт к неуспеху", 0.65),
    # s32: Systems - tripartite synapse
    ("This is reflected in the concept of the tripartite synapse, describing the importance of bidirectional communication between synapses formed by presynaptic and postsynaptic neurons and astrocytes [117].",
     "Фрагмент ведёт к неуспеху", 0.65),
]

spans = []
span_texts = set()
for i, (text, atype, conf) in enumerate(spans_raw):
    uid = f's{i+1}'
    start, end = find(text)
    color = '#81C784' if atype == 'Фрагмент ведёт к успеху' else '#EF9A9A'
    spans.append((uid, text, atype, start, end, color, conf))
    if start in goal_offsets:
        print(f'ERROR: {uid} (offset {start}) overlaps with {goal_offsets[start]}!')
        sys.exit(1)
    if text in span_texts:
        print(f'ERROR: duplicate span text for {uid}!')
        sys.exit(1)
    span_texts.add(text)

print(f'Spans: {len(spans)}')
print('OK: no span/goal overlaps, no duplicate spans')

# ============================================================
# RELATIONS - map each span to the goals it supports
# ============================================================

relations_map = [
    ('s1', 'g1'), ('s1', 'g6'),       # Fig1 hallmarks -> explored/focus
    ('s2', 'g1'), ('s2', 'g2'),       # rich body of knowledge -> explored/encourage
    ('s3', 'g5'), ('s3', 'g32'), ('s3', 'g33'), ('s3', 'g35'),  # nonlinear complexity -> need to explain, can't model simply, predictions hard, transfer functions
    ('s4', 'g3'), ('s4', 'g4'),       # pragmatic approaches -> speculate, anticipate
    ('s5', 'g4'), ('s5', 'g5'), ('s5', 'g49'), ('s5', 'g50'),  # conceptual change -> anticipate, explain, math clarity, evolve to exact science
    ('s6', 'g7'), ('s6', 'g8'),       # Mendelian forms -> confirmation pending, pose problems
    ('s7', 'g9'),                     # rural environment -> env factors elusive
    ('s8', 'g9'), ('s8', 'g10'),      # env/genetic correlations -> elusive, remain to be elucidated
    ('s9', 'g13'), ('s9', 'g14'),     # gut spreading -> Braak hypothesis, remains to be seen
    ('s10', 'g15'),                   # DA neuron anatomy -> not understood why center stage
    ('s11', 'g15'), ('s11', 'g16'),   # at-risk features -> not understood, speculated
    ('s12', 'g17'),                   # mito roles -> likely involved, unclear if causative
    ('s13', 'g18'),                   # heteroplasmy -> efforts not yielded answers
    ('s14', 'g19'),                   # PLA2G6/ATP13A2 -> mechanisms unknown
    ('s15', 'g20'),                   # multiple metals -> chelation under development
    ('s16', 'g21'),                   # 150K terminals -> synaptic vulnerability
    ('s17', 'g22'), ('s17', 'g23'),   # secondary effect -> etiology unclear, cause vs effect
    ('s18', 'g22'), ('s18', 'g23'), ('s18', 'g24'),  # microglia/astrocyte -> unclear, modulator
    ('s19', 'g24'), ('s19', 'g25'),   # microglia detect synuclein -> modulator, holistic needed
    ('s20', 'g26'), ('s20', 'g27'),   # nonlinear onset -> reductionist views fail, challenge key factors
    ('s21', 'g11'), ('s21', 'g12'),   # shared phenotypes -> tipping point, multiple hits
    ('s22', 'g34'), ('s22', 'g35'),   # spatiotemporal flow -> subsystem properties, transfer functions
    ('s23', 'g28'), ('s23', 'g43'), ('s23', 'g44'),  # added complexity -> efforts required, short-term goals, systems theory
    ('s24', 'g40'), ('s24', 'g45'), ('s24', 'g46'),  # symptomatic only -> disputable testing, need systems, not yet available
    ('s25', 'g46'), ('s25', 'g47'),   # 200 years symptomatic -> not available, need integration
    ('s26', 'g37'),                   # phenotypic buffering -> noninvasive approaches
    ('s27', 'g30'), ('s27', 'g31'),   # Wellstead -> theoretical models, models will help
    ('s28', 'g31'), ('s28', 'g36'),   # network modeling -> models will help, progress in decade
    ('s29', 'g38'), ('s29', 'g39'),   # biology+systems prerequisites -> microscopy, integration
    ('s30', 'g48'), ('s30', 'g49'),   # few fields more advanced -> signals, math clarity
    ('s25', 'g29'),                   # 200 years symptomatic -> ultimate aim translational
    ('s25', 'g41'),                   # 200 years symptomatic -> remains ambitious goal
    ('s3', 'g42'),                    # nonlinear complexity -> will pave way (explains why long road)
    ('s31', 'g25'),                   # energy metabolism integration -> holistic approaches needed
    ('s32', 'g25'),                   # tripartite synapse -> holistic approaches needed
]

relations = []
for i, (src, tgt) in enumerate(relations_map):
    relations.append((f'r{i+1}', src, tgt, 'ведёт к'))

print(f'Relations: {len(relations)}')

# Verify all goals covered
goal_uids = {g[0] for g in goals}
targeted = {r[2] for r in relations}
orphans = goal_uids - targeted
if orphans:
    print(f'WARNING: orphan goals: {sorted(orphans, key=lambda x: int(x[1:]))}')
else:
    print('OK: all goals have at least one span')

# Verify all span uids exist
span_uids = {s[0] for s in spans}
used = {r[1] for r in relations}
missing = used - span_uids
if missing:
    print(f'WARNING: missing spans in relations: {sorted(missing)}')

# ============================================================
# WRITE CSV
# ============================================================

output = io.StringIO()
output.write('# ANNOTATIONS\n')
output.write('uid,text,annotation_type,start_offset,end_offset,color,source,confidence\n')

for uid, text, atype, start, end, color, conf in goals + spans:
    escaped_text = text.replace('"', '""')
    output.write(f'{uid},"{escaped_text}",{atype},{start},{end},{color},file,{conf}\n')

output.write('\n# RELATIONS\n')
output.write('relation_uid,source_uid,target_uid,relation_type\n')
for ruid, src, tgt, rtype in relations:
    output.write(f'{ruid},{src},{tgt},{rtype}\n')

with open('annotations_Antony2013_PD.csv', 'w', encoding='utf-8', newline='') as f:
    f.write(output.getvalue())

print(f'\nCSV saved: {len(goals)} goals, {len(spans)} spans, {len(relations)} relations')
