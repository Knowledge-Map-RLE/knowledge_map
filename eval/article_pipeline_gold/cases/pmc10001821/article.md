# The Impact of Digital Coaching Intervention for Improving Healthy Ageing Dimensions among Older Adults during Their Transition from Work to Retirement

**Авторы:** Santini Sara, Fabbietti Paolo, Galassi Flavia, Merizzi Alessandra, Kropf Johannes, Hungerländer Niklas, Stara Vera

**Журнал:** International Journal of Environmental Research and Public Health (2023)

**DOI:** 10.3390/ijerph20054034


## Abstract

Retirement is a critical step in older adults’ lives, so it is important to motivate them to stay physically active, mentally healthy, and socially connected in the transition from work to retirement, including through digital health coaching programs. This study aims to: evaluate the impact of a digital coaching intervention to enhance three healthy ageing dimensions, i.e., physical activity, mental well-being, and socialization of a group of adults near retirement; understand the users’ experience; and identify the system strengths and weaknesses. This longitudinal mixed-methods study, carried out in 2021 in Italy and the Netherlands, enrolled 62 individuals. In the first 5 weeks of the trial, participants used a digital coach with the support of human coaches, and then they continued autonomously for another 5 weeks. The use of the digital coach improved the participants’ physical activity, mental well-being and self-efficacy during the first period and only the physical activity in the second. An effective coaching system should be flexible and attractive. High levels of personalization remain the golden key to aligning the health program to the physical, cognitive and social status of the intended target, thus increasing the user-system interaction, usability, and acceptability, as well as enhancing adherence to the intervention.


## 1. Introduction

We are witnessing the rapid ageing of the world population. The extension of life expectancy often means a prolonged disability condition in later life that is placing questions on long-term care systems across the world. The ageing of the population also entails the transition of many older adults from the status of workers to that of retirees. The literature now agrees that retirement is a critical step in people’s lives, full of opportunities and, at the same time, fraught with dangers [1,2]. In fact, alongside the greater availability of free time and the opportunity to use it in many activities, e.g., cultural and physical, the loss of meaningful relationships and interests can creep in, forcing older individuals to re-organize their daily schedule, re-negotiate their roles in the family and in society, and re-design, at least partly, their own identity [3].

Thus, the transition to retirement can represent the tipping point for healthy ageing or its opposite, based on the individuals’ response to this existential change. Healthy ageing is defined as “the process of developing and maintaining the functional ability (i.e., people’s capabilities of being and doing what they have reason to value) that enables well-being in older age” [4], whose main predictors are physical activity, mental well-being, and social participation [5,6].

There is a lack of consensus on how the retirement transition can affect older adults’ physical activity [7,8,9,10]. On the one hand, according to the activity theory, retirement may be an opportunity to increase physical activity. On the other hand, the literature underlines that during the retirement transition [11], there could be a fluctuation in the levels of intensity of, and in the motivation to do, physical activity, and a change in their types, which may be affected by gender as well. For example, according to a recent qualitative longitudinal study, the main driver of physical activity seems to be body shaping among men and socialization [12] among women.

Retirement can also influence individuals’ mental well-being and socialization. In fact, weaker and rarer meaningful social relationships, or a change in self-image, self-esteem, and self-efficacy [3] due to the end of the working life, can lead to social isolation, emotional discomfort, and depression [13].

Considering the above, it is very important to motivate older adults in the transition to retirement to stay physically active, mentally healthy, and socially connected so that they can age healthily and re-shape their own role in society without negative repercussions on their physical and mental health.

Health coaching interventions led by human coaches can motivate older adults to have healthier lifestyles in later life, for example, by eating more vegetables, practicing physical activity, and reducing cigarette smoking. Such programs often target individuals with chronic diseases and are aimed at helping patients determine and work toward their goals so that they become more compliant with the health program [14,15,16,17,18]. Health coaching programs, regardless of whether they are led by humans and/or by digital systems, mainly address older adults with chronic diseases, and only a few of them are conceived from a preventive perspective, targeting older adults in good health conditions and/or in transition to retirement [19]. On the contrary, healthy ageing strategies, including, for example, self-management capabilities, goal setting, personalised feedback and health literacy, as well as emotional support, reminders and alerts, could be highly effective for such a group of older adults, especially if in transition to retirement. Nevertheless, such strategies cannot often be managed by healthcare professionals because the available workforce cannot be devoted to education and prevention, being on the frontline of assistance to older patients with acute and chronic care needs. Thus, digital coaching technologies can offer an innovative way to overcome this lack of assistance and care as dialogue systems that sense relevant context, determine users’ intent, and provide feedback to improve users’ overall quality of life [20]. Therefore, digital coaching systems could be any computer program that supports spoken, text-based or multimodal conversational interactions with humans, such as personal digital assistants, virtual personal assistants, conversational agents or chats [21], reinforces and sustains healthy behavioural habits, and continuously monitors daily activities. There is still scant literature on the experience of older adults with digital coaching systems, but recent research showed that relatively young older adults may perceive digital coaching as a potential to motivate them towards physical activity by providing instructive information and motivational feedback [22]. Unfortunately, the efficacy of personal health coaching systems for adults over 55 remains unclear, and few examples are mapped in the field for older adults and even less for older people in transition from work to retirement [19,20]. This study is part of the AgeWell project aimed at co-designing and developing a digital coaching system (hereafter also referred to as Digital Coach-DC) targeting older adults aged 55 and over in the transition from work to retirement. The study aims to evaluate the impact of a digital coaching intervention to enhance physical activity, mental well-being, and socialization as three healthy ageing dimensions and help a meaningful retirement process as a factor influencing healthy ageing. It represents a novel contribution to assessing the value of digital coaching systems in a target population often overlooked by research on the development of this kind of technical solution. The purpose of the study was to answer three research questions: (1) To what extent can the AgeWell digital coach improve physical activity, mental well-being, social networking and the retirement process of older adults switching from work to retirement? (2) What was the experience of users with the digital coach? (3) What are the strengths and weaknesses of the system?


## 2. Materials and Methods

### 2.1. The System

The main aim of the system was to improve users’ healthy ageing attitudes and behaviours by providing them with a series of information and activities grouped into four areas: 1. physical activity; 2. social life; 3. emotional well-being; 4. good retirement. The system was tested as a mobile application (Android App) on a smartphone. For the study, participants were equipped with appropriate devices (Android Smartphone with Android version 8 and upwards), or they used their own devices when preferred and when the user’s private smartphone fulfilled the system’s technical requirements. The software used for the trial consisted of an avatar-based frontend (see Figure 1 below) running on a smartphone and a server component providing the content and collecting the data. Communication between the frontend and the backend was established over the Internet, using secure communication channels with an event-based technology (MQTT—Mosquitto MQTT Server v1.6.8 (Eclipse Foundation, Inc, Ottawa, ON, Canada) following MQTT protocol v3.1.1). The backend server ran within the facilities of one of the project consortium partners, to ensure privacy and security. No personal data were stored in the cloud or with third parties.


<figure>
  <figcaption><strong>Figure 1</strong> Home of the avatar-based app.</figcaption>
</figure>

Authentication was implemented using an OAuth2 broker service (www.auth0.com, accessed on 15 March 2020). The server components (see Figure 2 below) were implemented using the Karaf Java OSGi Framework and two databases: a NoSQL database (MongoDB, v3.6.8, MongoDB Inc., New York City, NY, USA) was used to store the user data gathered during App usage and to maintain the user preferences. In contrast, a SQL database (MariaDB, v10.1.29, MariaDB Corp., Espoo, Finland) (Eclipse Foundation, Inc, Ottawa, ON, Canada) was used for static content, e.g., the activities provided via the app. The server components ran on a Linux Virtual Machine (Ubuntu 18.04) (see Figure 3 below).


<figure>
  <figcaption><strong>Figure 2</strong> Overall components of the system.</figcaption>
</figure>


<figure>
  <figcaption><strong>Figure 3</strong> Components of the AgeWell server.</figcaption>
</figure>

The digital coach was co-designed with users through a user-centred design methodology that shaped the realization of four main functional areas stimulating and motivating older adults nearing retirement to improve their physical activity, mental well-being, socialization, and retirement process, as extensively reported in the Supplementary Materials (Table S1).

Among the physical activities to choose from, the app included: walking, tennis, swimming, dancing, and many others. The avatar asked users to choose the preferred activity to be inserted in a weekly plan and to decide on a personal goal. Thereafter, it sent motivational messages to help users reach such a goal, e.g., “Why stop now? You have already achieved so much” or “Once you really get into an exercise schedule, it just gets easier!”, and “Congratulations on making the commitment to exercise! Your body will thank you for it!”

The mental well-being function included three sub-functions: “Mind and body”; “Thought and action”; “Emotions and memories”. In the realm of “Mind and body”, the avatar proposed activities that promoted psycho-bodily well-being and were accompanied by links and/or video tutorials that facilitated their execution. They dealt with the ability to relax, calm down or even find dormant energies through meditation exercises or even more creative or expressive activities such as dancing and singing.

In the sub-realms of “Thought and action”, there were suggestions for activities that stimulated the subject to make plans and stick to them, to put themselves at the centre of their lives, or to remain flexible and see things from different points of view, e.g., the activity named “Bite your tongue!”, which invited users not to complain and pay attention to the positive events of their life.

Finally, in the sub-realm called “Emotions and memories”, there were some suggestions for activities that connect the person to his or her memories and ultimately give a sense of meaning and significance to one’s life, e.g., “Spend some time thinking about your success!” or “Strengthen the relationship with yourself!”.

The system also included activities for stimulating users’ new social contacts and improving the quality of their relationships, e.g., “Making new contacts!” and “Increase the quality of your friendships!”

Finally, the “Good retirement” function included three sub-functions: “Activities for retirement”; “Suggestions” on how to make retirement more meaningful; and “Information on retirement”. In this case, the avatar suggested specific activities that could help people leave the workplace in a healthy way, such as having a retirement party with colleagues or passing on to other younger colleagues their experience gained from years of work, as well as advice on how to garner information about the rights of retirees or even about the activities and facilities offered by one’s municipality of residence.


### 2.2. Study Design

In order to answer the three research questions, the study followed a mixed-methods design in which both qualitative (QUANT) and quantitative (QUAL) data were collected at three measurement times during the 10-week field trial. A concurrent equal status interactive mixed-methods research was adopted, where the QUANT and QUAL data components collection and analyses were executed simultaneously, having, therefore, the same value and being in constant interaction [23,24,25,26,27]. Two parallel QUANT and QUAL strands were integrated into meta-inferences after separate analyses were carried out. Thereafter, QUANT and QUAL results were brought together in the overall interpretation. The QUANT analysis was aimed at highlighting the effects of the digital coach on the physical health, mental well-being, socialization and retirement transition of participants (research questions 1 and 2). The QUAL analysis aimed at shedding light on the strengths and weaknesses of both the digital coach contents and technical aspects (research question 3). The point of integration of the two analyses was reached when the QUAL findings were added and integrated into the QUANT in order to explain to what extent the digital coach influenced users’ lifestyles and how much such an influence can be attributed to the system’s weaknesses and strengths.

As shown in Figure 4, in the first 5 weeks (Phase 1), participants were trained to use the digital coach by two human coaches, i.e., facilitators who constantly offered motivation, supported users’ confidence with the technology, provided technical skills and knowledge, and were responsible for the engagement of users. After the first 5 weeks (Phase 2), study participants continued to use the system without any help from the human coach. They could ask content-related questions and point out technical issues to their coaches via WhatsApp in Italy and via email in the Netherlands.


<figure>
  <figcaption><strong>Figure 4</strong> Study design.</figcaption>
</figure>

During the 5th and 10th weeks of usage, the human coaches administered two online group sessions for gathering users’ impressions about their experience with the system and three online questionnaires on system usability.

Since the COVID-19 pandemic was at the end of its second wave when the study started (May 2021), the study protocol was adapted in accordance with the global health crisis and the social restrictions for limiting the spread of the virus in the countries where the study was conducted. Thus, online questionnaires were adopted, and the link to them was sent to respondents by email instead of face-to-face administration. Moreover, several questions were added, e.g., on being infected with the virus and self-perception of the impact of the outbreak on individuals’ physical and mental health, in order to bring such variables under control as potential confounding factors.

The study started with the selection and enrolment of participants in every pilot site (Section 2.2.1). Then, the enrolled individuals were asked to answer an online questionnaire at baseline, after 5 weeks, and after 10 weeks of use of the technology. Along with the pilot, participants were also asked to attend three online group sessions led by a human coach, during which they were asked to answer some open-ended questions to describe their experience with the technology (Section 2.2.2). Then, the data collected were analysed, with QUANT data being analysed statistically and QUAL data being analysed thematically (Section 2.2.3).

#### 2.2.1. Inclusion Criteria and Recruitment Procedure

According to the AgeWell project activities, a sample of 100 participants was planned to be enrolled (50 in Italy and 50 in the Netherlands). Participants were contacted by phone in Italy and by email in the Netherlands, and they were screened through a battery of questions to check whether they met the inclusion criteria, i.e., being 55 or older, being three years before or three years after retirement, and feeling physically and cognitively healthy (see Figure 5 below). Although the statutory pension age is very similar in the two countries, i.e., 67 years in Italy and 66 years and four months in the Netherlands, without gender differences [28], the participants’ inclusion criteria were quite wide to also include all individuals who were exceptions to the general rule for different reasons, such as because they did demanding jobs such as those in the health sector or because the governments put in place extraordinary measures to facilitate the early exit from the labour market of certain workers’ categories.


<figure>
  <figcaption><strong>Figure 5</strong> Recruitment Procedure.</figcaption>
</figure>

In Italy, users were recruited through the research organization’s Human Resources office, voluntary associations and NGOs, private companies, and word of mouth. In the Netherlands, users were contacted by means of the NGO members carrying out the trial and other partner associations from the voluntary sector.

The individuals who agreed to take part in the study were provided with the informed consent form sent via email. Participants were asked to carefully read it, sign it for acceptance, and return it to the researchers by email. The two organizations involved in the trial evaluations applied for ethical approval by the respective competent ethics committees.


#### 2.2.2. QUANT and QUAL Data Collection Tools

In line with the study design, across the trial, life data were collected three times by questionnaires and twice by focus groups, whose tools are described in the following sub-paragraphs together with the analysis methods adopted. Thus, three questionnaires were drafted, one for every evaluation, i.e., before (T0, the baseline), at mid-term (T1, the 5th week of usage), and after the conclusion of the program (T2, the 10th week of usage). The questionnaires, besides demographic questions, consisted of three sections. The first section of the questionnaire focused on physical activity and well-being; the second focused on social life; and the third focused on participants’ experience with the technology. The first two sections of the second and third wave questionnaires (T1 and T2) were the same as the first wave (T0), except for the section on the technology that did not explore the experience with the ICT as at the baseline but instead delved deeper into users’ experience with the digital coach by means of two tools described in the paragraph headed “Quantitative outcome variables and data analysis”.

The structure of the group sessions with elders in both the study countries foresaw three meetings across the 10-week trial: before the trial, at the middle point, and one week after the end of the experimentation. The first meeting was aimed at training participants in the use of the system, and the other two were aimed at gathering their feedback on their experience with it in daily life as well as their reactions to its functions, usefulness and usability. Due to the pandemic, the meetings with the human coaches took place online.

In the first meeting, the human coaches showed the system functionality by sharing PowerPoint documents, videos, and smartphones running the system. Participants were also invited to try an activity together, e.g., a short demonstration of a mindfulness and body connection exercise as suggested by the system. In the second meeting, the human coaches asked participants how they were getting on with using the app and whether they had any technical problems, and they made room for further explanations to optimize the use of the system. At the third meeting, the human coaches led a focus group aimed at collecting users’ opinions on the system contents, technical aspects, impact on general health and well-being and suggestions for improvement.

The outcome variables answering the first research question are the SF-12v2 Health Survey [29] to measure the respondents’ physical health; the International Physical Activity Questionnaire (IPAQ) [30] to register the level of physical activity across the digital coach usage; the WHO-5 scale [31,32] and the General Self-Efficacy Scale (GSE-6) [33] to assess mental well-being; and the Lubben 6-item Social Network Scale (LSNS-6) [34,35] to measure the level of socialization.

The SF-12v2 Health Survey [29] is a 12-item subset of the SF-36v2. It is a brief, reliable measure of overall health status through two sub-scales of physical health (PCS) and mental health (MCS). Scores range from 0 to 100, with higher scores indicating better physical and mental health functioning. A score of 50 or less on the PCS-12 is recommended as a cut-off to determine a physical condition, and a score of 42 or less on the MCS-12 may indicate ‘clinical depression’ [36].

The IPAQ [30] identifies three levels of physical activity based on frequency and intensity of activities carried out in a week: high (i.e., approximately one hour of activity per day at an at least moderate intensity activity level), medium (i.e., equivalent to half an hour of at least moderate intensity physical activity on most days), and low (i.e., less than half an hour of moderate physical activity in a week).

The WHO-5 [31,32] scale score ranges from 0 to 25, with 0 representing the worst possible and 25 representing the best possible quality of life. The SF-12v2 mean score is set to 50.

The GSE-6 [33] measures the level of self-efficacy through six statements on which respondents must indicate the level of agreement and disagreement. The total score ranges between 5 and 25, with a higher score indicating more self-efficacy.

The total score of the Lubben 6-item Social Network Scale [34,35] is calculated by finding the sum of all items. The score ranges between 0 and 30, with a higher score indicating greater social inclusion. A cut-off of fewer than 12 points of the LSNS-6 is suggested to indicate social isolation, i.e., fewer than two people to perform social integration functions.

The outcome variables answering the second research question are the System Usability Scale (SUS) [37] and the User Experience Questionnaire (UEQ) [37]. The SUS is a Likert scale that includes 10 questions, which study participants ranked from 1 to 5 based on how much they agreed with the statement they were reading. A score of 5 means they agreed completely, and 1 means they strongly disagreed. The average SUS score is 68. Systems recording a score lower than 68 present severe usability problems. The UEQ scale [38] includes eight items: supportiveness, ease, efficiency, clearness, excitement, interest, inventiveness and leading edge. The questionnaire scales cover a comprehensive impression of user experience. Both classical usability aspects (efficiency, perspicuity, dependability) and user experience aspects (originality, stimulation) are measured. The range of the UEQ scales is between −3 (horribly bad) and +3 (extremely good). Values between −0.8 and 0.8 represent a neutral evaluation of the corresponding scale, values > 0.8 represent a positive evaluation, and values < 0.8 represent a negative evaluation.

The third research question was answered through QUAL data collected through the online meetings, during which open-ended questions were asked to stimulate users to think about the weaknesses and strengths of the system and offer suggestions for future digital coaches targeting elders about to retire.


#### 2.2.3. QUANT and QUAL Data Analysis

The QUANT outcome variables were analysed by country (Italy vs. the Netherlands) and by data collection times (T0 vs. T1 and T1 vs. T2) and then compared using the chi-square test for categorical variables and Student’s t-test for continuous variables. A probability value of <0.05 was considered statistically significant. Statistical analysis was performed using SPSS for Win V21.0. For the statistical analysis, only data coming from individuals filling in the questionnaire at the baseline (T0) and at least by the first and/or second follow-up (i.e., T1 and/or T2) and who answered more than ¾ of the questionnaire were considered. Data refer to 62 individuals, 34 from Italy and 28 from the Netherlands.

QUANT data are reported as mean (±SD) for continuous variables and as absolute frequencies for categorical variables.

The QUAL data, collected through the online meetings, were audio- and video-recorded after obtaining participants’ signatures on the informed consent form circulated before enrolment in the study and their verbal consent during the online session. Qualitative textual data arising from the transcriptions were analysed using the framework analysis method [39,40,41,42]. The text chunks were associated with codes systematized into a tree chart and combined under main themes. The latter were identified once the consistency within different codes under the same theme had been assessed. Repeated patterns/themes throughout the data set were identified, and a code was associated with every chunk of text. The content areas expressing similar concepts were grouped into mutually exclusive categories associated with codes. Two or more codes were combined, and different codes were sorted into themes and then quotes that were compared on a country basis. For the interpretation, data were rearranged according to the appropriate part of the thematic framework to which it related, and a matrix combining themes and countries was generated [42,43,44,45].

Therefore, the analysis started deductively from the aims and objectives of the study embedded in the topic guide but also reflected the respondents’ original observations according to an inductive approach. The parallel and independent analysis by three researchers minimized research bias [46,47,48,49,50]. The QUAL analysis trustworthiness was obtained by scholars’ checks and peer review [51].




## 3. Results

### 3.1. Sample Description

The first data collection wave was carried out with 91 people: 53 in Italy (19 older workers and 34 retirees) and 38 in the Netherlands (15 older workers and 23 retirees). Throughout the trial, 13 persons in Italy and 10 in the Netherlands dropped out (see Table 1 below). In Italy and in the Netherlands, the main reasons for dropping out were personal commitments and the lack of interest in the system.

Considering only individuals filling in the questionnaire at the baseline (T0) and at least by the first and/or second follow-up (i.e., T1 and/or T2) and who answered more than ¾ of the questionnaire, the final sample was made of 62 individuals, 34 from Italy and 28 from the Netherlands.

A total of 64.5% of the whole sample consisted of males (see Table 2 below), but with some differences between the national samples. In fact, in Italy, 55.9% of participants were females, while in the Netherlands, they were 10.7%. There was no difference at the country level concerning marital status, i.e., both in Italy and in the Netherlands, married people represented the majority (67.6% and 85.7%, respectively).

The Dutch participants were highly educated; 7 participants had completed between 9 and 13 years of education (25%) and 21 (75%) out of 28 participants had completed more than 13. The Italian participants had a more diverse educational level, with the majority having completed between 9 and 13 years of education (62%), almost a quarter more than 13 years of education (24%), and 15% between 6 and 8 years of education.

In the two countries, retirees represented most of the sample: 66.7% in Italy and 60.7% in the Netherlands.


### 3.2. The Impact of the AgeWell DC in Improving Healthy Ageing Dimensions

The percentage of participants perceiving their physical condition (SF-12-PCS) as having worsened, i.e., PCS ≤ 50, increased over the experimentation from 19.6% at T0 to 30.6% at T2, while their perception of their mental well-being (SF-12-MCS) remained stable, i.e., the percentage of respondents rating MCS ≤ 42 was 14.3% at T0 and at T2 (see Table 3 below). The pre-post intervention difference is statistically significant for both physical and mental well-being (p = 0.002 and <0.001, respectively).

The level of physical activity of participants increased significantly from T0 to T1 and then remained stable up to the end of the trial (p = 0.012). It is worth noting that the percentage of people practising a low level of physical activity decreased from 8.2% to 6% after the five trial weeks (the period with the support of the human coach), and it increased again once they started using the system autonomously (from 6% to 8.3%). The difference is statistically significant.

The participants’ mental well-being (WHO-5) and self-efficacy (GSE-6) slightly increased from T0 to T1, but they both decreased from T1 to T2. The level of socialization significantly decreased from T0 to T1 and increased from T1 to T2.


### 3.3. Users’ Experience with the AgeWell Digital Coach

Table 4 shows that out of the six dimensions of the UEQ (attractiveness, perspicuity, efficiency, dependability, stimulation, and novelty), only perspicuity reached a score >0.8, indicating a positive evaluation of the system. All the other dimensions received a bad evaluation by users over the system usage, with small fluctuations from T1 to T2 that only had an increasing trend for “efficiency”, reflecting a slight improvement of the system, while “attractiveness”, “dependability”, and “stimulation” decreased markedly. The system was not rated as “novel” by users from the start of the study onwards.

The usability score of the system (SUS) is 59, that is, 9 points lower than the average score of the scale (68), indicating that the system presents usability problems.

More than half of participants found the DC “moderately/very/extremely useful” after five weeks of usage, but, at the 10th usage week, less than half thought so. Looking at the different system areas of intervention, the percentage of people finding the system useful for “Enriching free time” decreased by 13.1% (from 67.3% to 54.2%), and that of people finding the DC useful for improving mental well-being dropped by 11.4% (from 63.5% to 52.1%). Conversely, participants discovered the usefulness of the AgeWell digital coach for approaching retirement smoothly over time despite initial skepticism; in fact, the percentage of users finding this function useful increased from 50% to 54.2% between T1 and T2.


### 3.4. Strengths and Weaknesses of the System

The QUAL analysis highlighted six main themes: 1. the digital coach’s contents’ strengths; 2. the digital coach’s contents’ weaknesses; 3. the human coach’s role; 4. the digital coach’s technical strengths; 5. the digital coach’s technical weaknesses; 6. users’ suggestions on contents and 7. on technical issues. Themes and sub-themes are briefly shown in Table 5 and analyzed in depth in the text below, supported by quotations extracted from the study participants’ answers, representing examples of opinions common to both Italian and Dutch participants or, conversely, a disagreement and, thus, national specificities. Beyond the information on the respondents’ identification number and country, the quotations from Italian respondents are also followed by information on gender and age (e.g., female, 58), which is not available for the Dutch participants because they did not give their consent to the disclosure of such data.

Concerning the content strengths, trial participants especially recognized the power of the system in five realms:Motivating users to increase their physical activity frequency and regularity: “I have had some benefits, for example from walking. Doing it for an hour a day at a steady pace is good for your health and the app makes me fulfill this commitment” (IT1, M, 65, retiree);Reminding them to perform activities: “I’m mainly using it as a reminder: it reminds me when I have to do something, some things I honestly do when the app reminds me” (IT3, M, 70, retiree);Helping users focus on their own needs (physical, psychological and social): “I have found the app very useful in helping me to focus a little on myself. In fact, I have a tendency to be focused on the needs of others, so someone reminding me “What do you do for yourself?” seems useful” (IT4, F, 65, retiree);Stimulating the activities proposed under the realms of mental well-being; some of them thought that several activities were really inspiring, e.g., activities about memories, photographs, yoga and relaxation exercises, or writing down their own qualities: “The app gave me inspiration to call my aunt and ask her to fix and rewrite her recipes. There are so many things that can be taken into account, maybe different from what we do every day” (IT7, M, 69, retiree). This opinion was common, especially among Italian respondents, while Dutch participants mentioned that they liked the proposed activities, but with great variety in the different healthy ageing realms, not only related to emotional well-being but with a wider perspective on the system empowerment capability: “I liked the assignment of being happy with things you have in your home, sending a card to family/friends, the reminder to do some volunteer work, plants” (NL32); “It fits well into my discipline, gives me inspiration and motivation” (NL5);Promoting a good retirement process: “It might be helpful for people in danger of falling into a void after retiring” (NL5) and “The digital coach managed to give me the motivation during the day or week to organize myself with new ideas, because a person who suddenly finds himself without work commitments can feel overwhelmed. The app helps you get organized and above all keeps you physically but also psychologically active, because it helps you organize your day, so for me it is useful by readying me for retirement” (IT10, F, 55, older worker).

Concerning the content weaknesses, study participants stressed that:Some physical activities proposed by the system were too physically demanding and not fully appropriate for elderly people, and users could not give reasons for not doing the suggested activities, thereby penalizing the overall rate at the end of the week: “On the other hand, the physical activity part that marks the day is not suitable for us. It is not that we do not move around but, for example, on Sunday we usually go for an excursion because we like to walk, but we have done 2 days of heavy gardening, so yesterday we did not feel like walking” (IT43, F, 59, older worker);The system was quite rigid, not customizable and not flexible: “What bothers me is the daily activity that is automatically inserted and that I cannot remove” (IT4, F, 65; retiree) and “Planning is tricky, also because I work part-time. (I would prefer not to have a) split between working and not working (retirement). I am not able to fill the day because of work, and my activities like walking dogs and dog training do not fit in (the app)” (NL038);The constant pressure the DC put on users by asking them to report the performance was unpleasant: “I would prefer it to be an inspiration tool, not an administration tool” (NL4).

The main technical strength of the system underlined by all participants was the use of videos and video tutorials, as they were considered inspiring and useful for motivating users to put into practice what the videos showed, regardless of the type of activity and the realm it belonged to, e.g., physical activity or psychological well-being, as depicted by the following quotations: “When I was on holiday, I also went to see all the videos that the app offers and they are nice, because they can be stimulating and can make you want to do one thing or the other” (IT12, F, 67, retiree) and “Yoga video clips worked well and fitted [the program of] the gym” (NL09).

Both Italian and Dutch participants stressed the following technical weaknesses:Problems in registering/changing the activities they had done. Dutch participants also complained about the long time the platform took to load and the pop-up that mentioned “attempts”;Problems with the daily plan, finding it annoying, and preferring a weekly and personalized plan: “I thought it would also be easier and more intuitive to record the activities carried out so that the activity icons in the various sections would be colored. You have to go and click on “I have done it”, but there was one time when it did not record it and I had to go back to it” (IT03, M, 70, retiree);The lack of intuitiveness and flexibility: “The logic of the app is not good. It is unpleasant to work with, not user friendly. (This is an) important downside” (NL027);The unclearness of graphs reporting daily activity rates: “Overview of notifications is missing in the app. It is tricky that you cannot fill in anything for the day before. Planning something extra on the day itself is not possible” (NL035);The avatar was annoying and boring (especially for Italian users), and it had no added value, especially for Dutch users. The latter found the way it looked and sounded not fun and very negative because the avatar repeated messages many times, and it was not interactive. The voice of the avatar was deemed unpleasant and sometimes boring: “Remarks like ‘doing the dishes and cleaning up works well for me’, reminders and specifically derogatory comments like ‘keep it up’ were fake” (NL014).

Suggestions coming from the experimentation mainly concern system contents and technical aspects. Regarding the contents, the users suggested to: Personalize activities as much as possible, including by adding other activities such as reading, volunteering and nutrition: “The reading activity does not seem so much specified by the app, maybe less in summer, but in winter it would be better to add it and maybe the app should be diversified on a seasonal basis, in my opinion” (IT9, M, 61, retiree), and “To add other activities”, e.g., volunteering (NL10), nutrition (NL04), gym (NL036);Plan periodical meetings with the human coach: “I suggest that every now and then there is a confrontation with the coach, that is, a contact or a video call or a physical meeting (…) I believe that a tool of this kind can be useful, but it must be interspersed with personal relationships, not even with videoconferencing, rather private talk, once with a psychologist, once with a trainer, another time with an expert of any another thing, because it is the relationship that gives us the opportunity to grow, to improve, in my opinion, in terms of both physical and psychological well-being” (IT52,F, 69, retiree);Explaining what every proposed activity is useful for in order to further motivate the user to do it: “I could not lend myself to really doing those categories or activities, when I do not know what it is useful for. What does it bring me?” (NL11).

Concerning technical issues, users proposed to:Make the app more intuitive: “If there was some more automatic and intuitive function, it would be better, because you always have to go there, see if it works, wait for it to turn and load” (IT03, M, 70, retiree);Launch activities with movies and videos to motivate people to perform the activities: “It would be a good idea to start with a movie clip (that) begins with explaining why I should do this activity” (NL11);Connect the app activity plan to the smartphone agenda: “The app should link to the agenda on your phone” (ID4).



## 4. Discussion

The novelty of the study lies in testing the impact of a digital coach in motivating elders aged 55 and older in transition to retirement, an overlooked group of users, to adopt healthy ageing lifestyles through several activities proposed via four functionalities addressing healthy ageing components, i.e., physical activity, mental well-being, and socialization and retirement.

### 4.1. Towards Tailored and Attractive Digital Coach Systems

QUANT findings showed that the use of the AgeWell digital coach improved participants’ level of physical activity, mental well-being, and self-efficacy during the first 5 weeks of experimentation, when users were supported by the human coach. It is nevertheless worth noting that after the human coach stopped his/her activity, this positive effect continued only for the physical activity, but not for the mental well-being and self-efficacy. On the one hand, these QUANT results suggest that the digital coach systems can stabilize fluctuations in the physical activity performed by older adults before and after retirement [10,11]. On the other hand, the users’ desire to have periodical meetings with the human coach, evidenced by the QUAL results, may suggest that, for this generation of older adults, it is still important to have the mediation of a human coach to also effect their mental well-being, which is exposed to risk during the retirement process [3,13]. This suggests that the current version of digital health coaching systems cannot fully replace human-led interventions and may not be as effective as those led by human coaches [14,15,16,17,18].

Moreover, QUANT findings tell us that the level of socialization among participants worsened as the trial proceeded during both the human and the digital coach-driven phase. A possible explanation of this result may lie in the fact that, although the number of opportunities for social contacts increased thanks to the periodical distance meetings with the human coach and other users, the virtual nature of these contacts was not so gratifying and satisfying as to improve the perception of the quality of participants’ social ties. In fact, the trial took place between May and October 2021, when many social restrictions were still in force due to the COVID-19 pandemic, and elders participating in the experimentation might have suffered from the medium-term effects of two years of physical distancing. As a result, they might need personal contact with peers to experience meaningful relationships, as in the pre-pandemic period. In fact, although the QUAL findings show that several participants, especially in Italy, appreciated the function of the digital coach stimulating them to keep in contact with friends and relatives, this was not sufficient to improve participants’ capability of increasing the number or the quality of social ties. The existing literature agrees on the fact that technology can improve many dimensions of social connection among older adults, e.g., by communicating and sharing not only pictures and media but also emotions and states of mind and by reading news and books [52,53,54].

This highlights the need to design digital coaching systems that are capable of doing this and accordingly improve socialization among older adults.

Furthermore, both QUANT and QUAL results showed that user experience with the system was not positive in either country. In fact, users found the system unintuitive, not user-friendly and not flexible. Dutch users were particularly attentive to the technical aspects, which is probably due to a greater diffusion of digital systems in this country and to greater digital health literacy among its senior citizens compared to their Italian counterparts, which led them to have higher expectations regarding digital coach systems. Moreover, users did not like the appearance and the attitude of the avatar, which was considered rigid and excessively directive, especially by Italian respondents.

In addition to what Kettunen, Kari and Frank [22] suggested, i.e., that digital coaching devices must be tailored and easy to learn to be attractive to older adults, the above indicates that a key point for the digital coach to be accepted by this target population is the capability of being flexible, funny, interesting, and attractive without being too directive. A characteristic common to older adults in retirement, in fact, is the willingness to be masters of their own life and time, which means being in the condition of choosing what to do with full autonomy in real and digital activities alike [55].

Furthermore, the increased number of users who appreciated the function aimed at making the transition to retirement easier over the experimentation time frame suggests the need for an app that can stimulate healthy ageing during this existential change. This also implies the need for further studies targeting this population group and their experience with digital coaches. The latter should be based on customizable avatars, which is one of the most critical issues that emerged in other studies as well [56,57,58].

In light of the above, the improvement in system usability could also enhance the impact on individuals’ health and well-being.


### 4.2. Strengths and Limitations

The strength of the study is the adoption of a mixed-method approach, which allowed the interpretation of apparently contradictory findings highlighted by QUANT and QUAL tools.

Although the QUAL results highlighted the capability of the system to stimulate older adults to behave in a way more oriented to healthy ageing principles, the numerous technical issues might have confounded the users’ perception of the contents and dimmed the full potential of the app in helping elderly people smoothly cross the line of retirement. This represented a significant limitation of the study, together with the low number of participants, whose recruitment was hindered by the COVID-19 pandemic only in Italy and The Netherlands. Moreover, it was hard to engage older workers in the trial because they had more time constraints than retirees, who represented the majority of the sample. In addition, as a limitation of the study design, the lack of a control group, as well as the length of the trial, did not permit us to go in depth into the effectiveness of the system. All these limitations did not allow for a generalization of results.

Therefore, future large sample studies are encouraged to assess the impact and the effectiveness of digital coach systems in promoting healthy ageing within this elderly population group. Finally, the use of a usable and tailored digital coach may have a positive impact not only on older individuals but also at the company level if we consider older adults near retirement as older workers from a work and human capital perspective [59]. In fact, although there is no difference in productivity between younger and older workers, the latter have more absenteeism than the former [60], representing a huge loss in productivity, as hugely emerged during the COVID-19 outbreak [61]. Although the relationship between age and sickness absence among older workers is not well understood [62], there is a certain concern about it, considering the massive amount of the workforce that is ageing [63].



## 5. Conclusions

This study showed that a digital coaching program can be a valuable tool to stimulate older adults to adopt healthy lifestyles while they cross the line of retirement, especially by triggering physical activity. On the contrary, mental well-being and socialization remain the most difficult healthy ageing dimensions to be addressed by digital coach technology. Thus, there is still a need for the support of a human coach in attaining positive mid-term outcomes in these realms. Within this study, some empirical evidence about the characteristics that a coaching system must possess have been highlighted: flexibility, to address the needs of this specific target; being interesting and attractive, to stimulate proactivity and healthy ageing habits during this existential change; and offering a polite communication mode exchange, since elders in retirement want to maintain control over their life and time. Indeed, the level of personalization of such coaching systems remains the golden key to aligning the health program to the physical, cognitive and social status of the intended target. In addition, it can significantly impact the quality of the user-system interaction, usability, and acceptability, as well as enhance adherence to the intervention. Even if technology-based interventions such as coaching systems are an emerging field in the healthcare domain, it seems that there is still a lack of evaluations to discover the added value of this innovation.


## References

1. MarmotM.
WilkinsonR.G.
Health and the Psychosocial Environment at WorkSocial Determinants of Health2nd ed.Oxford University PressStrasbourg, France200613: 9780198565895

2. Tobiasz-AdamczykB.
BrzyskiP.
Psychosocial work conditions as predictors of quality of life at the beginning of older ageInt. J. Occup. Med. Environ. Health200518435216052890

3. LucasA.R.
DanielF.
GuadalupeS.
Massano-CardosoI.
VicenteH.
Time spent in retirement, health and well-beingEur. Psychiatry20174133934010.1016/j.eurpsy.2017.02.298

4. World Health Organization
World Report on Aging and HealthWHOGeneva, Switzerland20159789240694811

5. Bosch-FarréC.
Garre-OlmoJ.
Bonmatí-TomàsA.
Malagón-AguileraM.C.
Gelabert-VilellaS.
Fuentes-PumarolaC.
Juvinyà-CanalD.
Prevalence and related factors of Active and Healthy Aging in Europe according to two models: Results from the Survey of Health, Aging and Retirement in Europe (SHARE)PLoS ONE201813e020635310.1371/journal.pone.020635330372472PMC6205806

6. European Commission
Green Paper on Aging2021Available online: https://ec.europa.eu/info/sites/info/files/1_en_act_part1_v8_0.pdf(accessed on 9 January 2023)

7. AtchleyR.C.
A continuity theory of normal ageingGerontologist19892918319010.1093/geront/29.2.1832519525

8. AtchleyR.C.
Social Forces and Aging9th ed.Wadsworth PublishingBelmont, CA, USA20009780534043384

9. HenningG.
StenlingA.
BielakA.A.
BjälkebringP.A.
GowJ.
KiviM.
Muniz-TerreraG.
BooJ.B.
LindwallM.
Towards an active and happy retirement? Changes in leisure activity and depressive symptoms during the retirement transitionAging Ment. Health20212562163110.1080/13607863.2019.170915631965817

10. McDonaldS.
O’BrienN.
WhiteM.
SniehottaF.F.
Changes in physical activity during the retirement transition: A theory-based, qualitative interview studyInt. J. Behav. Nutr. Phys. Act.2015122510.1186/s12966-015-0186-425889481PMC4343052

11. Van DyckD.
CardonG.
De BourdeaudhuijI.
Longitudinal changes in physical activity and sedentary time in adults around retirement age: What is the moderating role of retirement status, gender and educational level?BMC Public Health201616112510.1186/s12889-016-3792-427793134PMC5084354

12. SocciM.
SantiniS.
DuryS.
Perek-BiałasJ.
D’AmenB.
PrincipiA.
Physical Activity during the Retirement Transition of Men and Women: A Qualitative Longitudinal StudyBiomed. Res. Int.202130272088510.1155/2021/2720885PMC842354434504896

13. KolodziejI.W.K.
García-GómezP.
Saved by retirement: Beyond the mean effect on mental healthSoc. Sci. Med.2019225859710.1016/j.socscimed.2019.02.00330822608

14. WoleverR.Q.
SimmonsL.A.
SforzoG.A.
DillD.
KayeM.
BechardE.M.
SouthardM.E.
KennedyM.
VoslooJ.
YangN.
A systematic review of the literature on health and wellness coaching: Defining a key behavioral intervention in healthcareGlob. Adv. Health Med.20132385710.7453/gahmj.2013.042PMC383355024416684

15. Neuner-JehleS.
SchmidM.
GrüningerU.
The “Health Coaching” programme: A new patient-centred and visually supported approach for health behaviour change in primary careBMC Fam. Pract.20131410010.1186/1471-2296-14-10023865509PMC3750840

16. BodenheimerT.
Willard-GraceR.
GhorobA.
Expanding the roles of medical assistants: Who does what in primary care?JAMA Intern. Med.20141741025102610.1001/jamainternmed.2014.131924820220

17. BarkerA.
CameronP.
FlickerL.
ArendtsG.
BrandC.
Etherton-BeerC.
ForbesA.
HainesT.
HillA.
HunterP.

Evaluation of RESPOND, a patient-centred program to prevent falls in older people presenting to the emergency department with a fall: A randomised controlled trialPLoS Med.201916e100280710.1371/journal.pmed.100280731125354PMC6534288

18. HibbardJ.
GilburtH.
Supporting People to Manage Their Health: An Introduction to Patient Activation LondonThe King’s FundLondon, UK2014Available online: https://www.kingsfund.org.uk/sites/default/files/field/field_publication_file/supporting-people-manage-health-patient-activation-may14.pdf(accessed on 9 January 2023)

19. StaraV.
SantiniS.
KropfJ.
D’AmenB.
Digital Health Coaching Programs Among Older Employees in Transition to Retirement: Systematic Literature ReviewJ. Med. Internet Res.202022e2506510.2196/2506532969827PMC7545329

20. BevilacquaR.
CasacciaS.
CortellessaG.
AstellA.
LattanzioF.
CorsonelloA.
D’AscoliP.
PaoliniS.
Di RosaM.
RossiL.

Coaching Through Technology: A Systematic Review into Efficacy and Effectiveness for the Ageing PopulationInt. J. Environ. Res. Public Health202017593010.3390/ijerph1716593032824169PMC7459778

21. McTearM.
Conversational AI: Dialogue systems, conversational agents, and chatbotsSynthesis Lectures on Human Language TechnologiesSpringerBerlin/Heidelberg, Germany2020Volume 13125110.2200/S01060ED1V01Y202010HLT048

22. KettunenE.
KariT.
FrankL.
Digital Coaching Motivating Young Elderly People towards Physical ActivitySustainability202214771810.3390/su14137718

23. MorseJ.M.
Approaches to qualitative-quantitative methodological triangulationNurs. Res.19914012012310.1097/00006199-199103000-000142003072

24. MorseJ.M.
NiehausL.
Mixed Method Design: Principles and Procedures1st ed.RoutledgeNew York, NY, USA200910.4324/9781315424538

25. CreswellJ.W.
ClarkV.L.P.
Designing and Conducting Mixed Methods Research3rd ed.Sage PublicationsThousand Oaks, CA, USA2017

26. GreeneJ.C.
Preserving Distinctions within the Multimethod and Mixed Methods Research Merger
Hesse-BiberS.
Burke JohnsonR.
Oxford University PressNew York, NY, USA2015

27. SchoonenboomJ.
JohnsonR.B.
How to Construct a Mixed Methods Research DesignKoln. Z. Fur Soziologie Und Soz.20176910713110.1007/s11577-017-0454-1PMC560200128989188

28. Eurostat
Ageing Europe—Statistics on Working and Moving into Retirement. Eurostat Statistics Explained2023Available online: https://ec.europa.eu/eurostat/statistics-explained/index.php?title=Ageing_Europe_-_statistics_on_working_and_moving_into_retirement#Older_people_moving_into_retirement(accessed on 10 February 2023)

29. WareJ.Jr.
KosinskiM.
KellerS.D.
A 12-Item Short-Form Health Survey: Construction of scales and preliminary tests of reliability and validityMed. Care19963422023310.1097/00005650-199603000-000038628042

30. LeeP.H.
MacfarlaneD.J.
LamT.H.
StewartS.M.
Validity of the International Physical Activity Questionnaire Short Form (IPAQ-SF): A systematic reviewInt. J. Behav. Nutr. Phys. Act.2011811510.1186/1479-5868-8-11522018588PMC3214824

31. ToppC.W.
ØstergaardS.D.
SøndergaardS.
BechP.
The WHO-5 Well-Being Index: A Systematic Review of the LiteraturePsychother. Psychosom.20158416717610.1159/00037658525831962

32. WHO
Wellbeing Measures in Primary Health Care/The Depcare ProjectWHO Regional Office for EuropeCopenhagen, Denmark1998Available online: https://apps.who.int/iris/handle/10665/349766(accessed on 9 January 2023)

33. RompellM.
HerrmannC.
WachterR.
EdelmannF.
PieskeB.
GrandeG.
A short form of the General Self-Efficacy Scale (GSE-6): Development, psychometric properties and validity in an intercultural non-clinical sample and a sample of patients at risk for heart failurePsychosoc. Med.20131010.3205/psm000091PMC357820023429426

34. LubbenJ.
Assessing social networks among elderly populationsFam. Community Health J. Health Promot. Maint.1988114252Available online: http://www.jstor.org/stable/44953053(accessed on 2 September 2022)10.1097/00003727-198811000-00008

35. LubbenJ.
BlozikE.
GillmannG.
IIiffeS.
von Renteln KruseW.
BeckJ.C.
StuckA.E.
Performance of an abbreviated version of the Lubben Social Network Scale among three European Community–dwelling older adult populationsGerontologist20064650351310.1093/geront/46.4.50316921004

36. WareJ.
KosinskiM.
KellerS.
SF-12: How to Score the SF-12 Physical and Mental Summary Scales2nd ed.The Health Institute, New England Medical CenterBoston, MA, USA1995

37. BrookeJ.
Usability Evaluation in Industry1st ed.Taylor and FrancisLondon, UK1996

38. LaugwitzB.
SchreppM.
HeldT.
Construction and evaluation of a user experience questionnaireHCI and Usability for Education and WorkSymposium of the Austrian HCI and Usability Engineering GroupWalldorf, Germany2008637610.1007/978-3-540-89350-9_6

39. DeSantisL.
UgarrizaD.N.
The Concept of Theme as Used in Qualitative Nursing ResearchWest. J. Nurs. Res.20002235137210.1177/01939459000220030810804897

40. BraunV.
ClarkeV.
Using thematic analysis in psychologyQual. Res. Psychol.200637710110.1191/1478088706qp063oa

41. VaismoradiM.
BondasT.
TurunenH.
Content Analysis and Thematic Analysis: Implications for Conducting a Qualitative Descriptive StudyJ. Nurs. Health Sci.2013539840510.1111/nhs.1204823480423

42. PlatS.
Thematic Analysis Software: How It Works & Why You Need ItAvailable online: https://getthematic.com/insights/thematic-analysis-software/(accessed on 9 January 2023)

43. MayringP.
Qualitative content analysisForum Qual. Soc. Res.20001Available online: https://www.qualitative-research.net/index.php/fqs/article/view/1089(accessed on 9 January 2023)

44. MorettiF.
van VlietL.
BenzingJ.
DeleddaG.
MazziM.
RimondiniM.
ZimmermannC.
FletcherI.
A standardized approach to qualitative analysis of focus group discussions from different countriesPatient Educ. Couns.20118242042810.1016/j.pec.2011.01.00521292424

45. RabieeF.
Focus-group interview and data analysisProc. Nutr. Soc.20046365566010.1079/PNS200439915831139

46. GubaE.G.
LincolnY.S.
Competing paradigm in qualitative researchHandbook of Qualitative Research5th ed.
DenzinN.K.
LincolnY.S.
SageThousand Oaks, CA, USA1994105117

47. MorseJ.
BarrettM.
MayanM.
OlsonK.
SpiersJ.
Verification Strategies for Establishing Reliability and Validity in Qualitative ResearchInt. J. Qual. Methods20021132210.1177/160940690200100202

48. SlevinE.
SinesD.
Enhancing the truthfulness, consistency, and transferability of a qualitative study: Using a manifold of approachesNurse Res.20007799810.7748/nr2000.01.7.2.79.c6113

49. FraserS.
GreenhalghT.
Coping with complexity: Educating for capabilityBMJ200132379980310.1136/bmj.323.7316.79911588088PMC1121342

50. SandelowskiM.
Rigor or rigor mortis: The problem of rigor in qualitative research revisitedANS Adv. Nurs. Sci.1993161810.1097/00012272-199312000-000028311428
