# Managing Mortality and Aging Risks with a Time-Varying Lee–Carter Model

**Авторы:** Chen Zhongwen, Shi Yanlin, Shu Ao

**Журнал:** Healthcare (2023)

**DOI:** 10.3390/healthcare11050743


## Abstract

Influential existing research has suggested that rather than being static, mortality declines decelerate at young ages and accelerate at old ages. Without accounting for this feature, the forecast mortality rates of the popular Lee–Carter (LC) model are less reliable in the long run. To provide more accurate mortality forecasting, we introduce a time-varying coefficients extension of the LC model by adopting the effective kernel methods. With two frequently used kernel functions, Epanechnikov (LC-E) and Gaussian (LC-G), we demonstrate that the proposed extension is easy to implement, incorporates the rotating patterns of mortality decline and is straightforwardly extensible to multi-population cases. Using a large sample of 15 countries over 1950–2019, we show that LC-E and LC-G, as well as their multi-population counterparts, can consistently improve the forecasting accuracy of the competing LC and Li–Lee models in both single- and multi-population scenarios.


## 1. Introduction

The ongoing improvement of human life expectancy around the world has far-reaching influences on many aspects of our society. For instance, Maestas et al. [1] highlight the importance of considering demographic changes, including mortality projections, in analyzing labor supply. Mortality projections are used to predict future changes in the size and age structure of the labor force, which can help inform policy decisions related to workforce development and training, immigration, and other factors that affect the labor market. For the healthcare system, Fenton et al. [2] indicate the importance of considering changes in mortality projections in analyzing healthcare utilization and expenditure. Specifically, prediction of future demand for health and medical care services is dependent on mortality projections. Such predictions may inform policy decisions related to the allocation of resources for healthcare and the design of related systems. The importance of accurate mortality projections is also witnessed in retirement and pensions and the insurance industry (see, for example, ref. [3], among others).

To better model the underlying patterns of mortality improvement is, therefore, essential to enhance accuracy of mortality projection. Among the existing studies, Lee and Carter [4] is the mostly widely used factor-based mortality model, known as the LC model. Despite its popularity, the LC model assumes constant age-specific mortality decline speeds over time. Therefore, the LC model produces increasingly large proportional differences in the projected death rates, even at adjacent ages, in the long run. Specifically, the projected mortality rates of LC are implausibly low for infants and younger ages relative to older ages. This is in contrast to the findings in influential studies, including Li et al. [5], that found that mortality declines at younger ages have been slowing while declines at older ages have been accelerating.

A “rotation” approach of age-specific mortality decline speed was later proposed by Li et al. [5] to enhance the LC model. However, this rotation is of an ad hoc nature rather than being data-driven [6]. To address this, we investigate a time-varying coefficients extension of the LC model. Simply speaking, we employ a local constant kernel smoothing method [7] to model and forecast dynamic age-specific mortality declines. In this paper, we consider two commonly adopted kernel functions: Epanechnikov and Gaussian, and the corresponding extensions of the LC model are denoted by LC-E and LC-G, respectively. Technical details of the modelling approach are provided, and our empirical results consider data of 15 low-mortality populations sourced from the famous Human Mortality Database [8], including annual mortality rates of age 0–100 spanning 1950–2019.

The contributions of this paper are threefold. First, the proposed time-varying coefficients extension of the LC model effectively complements the rotation adopted in Li et al. [5]. The proposed flexible framework ensures that the speed of rotation is data-driven, rather than ad hoc. The existence of closed-form solutions further makes the proposed extension computationally efficient. Secondly, using a comprehensive population dataset, we systematically demonstrate the outstanding performance of the time-varying models. The overall superiority of the LC-E and LC-G models is robust when the age and temporal setting are changed. The analysis of life expectancies up to 2100 further shows that the LC-G model can well address the issue of underestimated mortality improvements at old ages, existing for the LC model [5]. Thus, the LC-E and LC-G models may provide potentially more accurate forecasts than the LC model in the research regarding long-term mortality projection. Finally, we describe the multi-population extensions of the employed models and illustrate their forecasting performances. Consistent with the single-population case, the newly proposed multi-population extensions are still overall the best performing model among all investigated specifications.

The rest of this paper is structured as below. Section 2 describes the data and models. We present empirical results with discussions in Section 3. Section 5 concludes the paper.


## 2. Data and Methods

### 2.1. Database

To study the mortality rates, the data of this paper are sourced from the famous Human Mortality Database [8], or HMD. HMD provides detailed mortality and population data for over 40 developed countries. We employ the annual age-specific central mortality rates, which are derived from official statistics from each country. HMD is maintained by the Max Planck Institute for Demographic Research in Rostock, Germany, and the University of California, Berkeley, United States of America (USA). As stated in its official website, the purpose of HMD is to make mortality data available for scientific research and to promote research in social sciences, such as actuarial studies, demographics, labor economics, and public health and care.

In order to study the consistent mortality declines, we explore 15 low-mortality countries as considered in Li and Lee [9]: Australia (instead of West Germany), Austria, Canada, Denmark, the United Kingdom, Finland, France, Italy, Japan, the Netherlands, Norway, Spain, Sweden, Switzerland, and the USA. For the low-mortality nature, mortality rates are more likely to consistently decline across all ages. This enables one to observe the potential rotating patterns on age-specific mortality rates, as argued by Li et al. [5]. Following Booth et al. [10], we choose an opportune range of data starting from 1950 to 2019 in order to have a reliable and complete dataset. The crude uni-sex (total) mortality data for ages 0–100 are studied in this paper.

We present logged mortality rates averaged across the 15 populations in Figure 1. Consistent mortality declines are observed at all ages over time. Appropriate modelling of those patterns is critical to credible mortality projections, which is the key to the accurate actuarial, demographic, and healthcare practices (see, for example, refs. [11,12,13,14], among others).


<figure>
  <figcaption><strong>Figure 1</strong> Averaged logged mortality rates.</figcaption>
</figure>


### 2.2. The Lee–Carter and Related Models

Suppose we have mortality data of N ages, each age with T years of observations. The Lee–Carter (LC) model (1992) ([4]) summarizes the systematic mortality trends of the N ages by a common factor. Formally, the log central mortality rate at age x in year t, lnmx,t, follows the specification given by:(1)lnmx,t=ax+bxkt+εx,t,
where ax is the mortality level, i.e., the average mortality rate over time at age x, kt is the period effect, i.e., the systematic mortality trend common to all ages, bx is the age effect at x, i.e., the sensitivity of lnmx,t to kt, and εx,t is the normal residual term with mean 0 and variance σεx2. As noted by [4], Equation (1) is not identifiable without normalization constraints. For example, one could multiply bx with a constant c and divide kt by the same constant and reach the same fitting results. In [4], the following normalization constraints are imposed:∑tkt=0,and∑xbx=1.

Given the constraint of kt, ax is set to the mean of lnmx,t over the sample considered. The LC model is then estimated by singular value decomposition (SVD) instead of the usual ordinary least square approach in the original paper. (A maximum likelihood estimation method may also be employed to calibrate the parameters [15]. Alternatively, a Bayesian approach is proposed in Li et al. [16]. Compared to those estimation methods, SVD is much more computationally efficient and stable, which is critical to the proposed time-varying framework of this paper.)

While ax and bx are assumed to be constant, the period effect is often modeled by a time-series process. In particular, ref. [4] assumes a random walk with drift specification, which is adopted by many later studies:(2)kt=kt−1+d+et,
where the drift term d measures the average annual change in kt, and et∼i.i.d.N(0,σe2). Based on the time-series specification in Equation (2), future mortality rates can be projected by extrapolating the period effect kt. Specifically, the expected h-step-ahead mean forecasts of the period effect and the log central death rate are given by:(3)k^T+h=kT+hd,lnm^x,T+h=a^x+b^xk^T+h,
where T is the last year of the sample.


### 2.3. Issues with the Lee–Carter Model and Related Literature

For the long-spanning nature of mortality data, the static parametric structure of the LC model may not be compatible with reliable long-term demographic research. To see this, the specification of the LC model decomposes mortality improvements into the product of latent non-stationary mortality trend factors (kt), assumed as a random walk with drift, and the corresponding age specific loadings of these trends (bx), assumed constant over time. Considering the data displayed in Figure 1, we plot the fitted bx using a rolling window of a 30-year width in Figure 2. (There are no available data for the first 29 time points (i.e., 1950–1978) using the rolling window approach.) Clearly, the fitted bx becomes roughly “flatter” over time, with decreasing (increasing) weights for the younger (older) ages. Ignoring such a dynamic pattern therefore reduces the credibility of the forecast mortality rates and life expectancies of LC. Even when the BMS model is used, the static parametric nature is not necessarily sufficient to address this issue.


<figure>
  <figcaption><strong>Figure 2</strong> Dynamic age-specific declines b^x,t.</figcaption>
</figure>

The insufficiency of the static bx over time is recognized in the influential work by Li et al. [5]. To resolve it, a “rotation” approach is proposed, which specifies that the out-of-sample b^x will be dynamic and gradually converge to an ultimate structure. However, such an ultimate structure is determined by expert (ad hoc) judgments rather than being data-driven [6].


### 2.4. A Time-Varying Coefficients Extension of the Lee–Carter Model

To systematically address the ad hoc issue of Li et al. [5], we investigate a time-varying coefficients extension of the LC model. Specifically, we employ a local constant kernel smoothing method [7], also known as the Nadaraya–Watson estimator, to accommodate the dynamics in the age-specific mortality declines. A novel application of such an estimator in mortality forecasting can be found in Chang and Shi [19]. This approach allows bx to be time-dependent over both the in-sample (denoted by bx,t) and out-of-sample (denoted by bx,T+h) periods. In this paper, we consider two commonly adopted kernel functions: Epanechnikov and Gaussian, and the corresponding extensions of the LC model are denoted by LC-E and LC-G, respectively. The technical details are described in this section.

#### 2.4.1. A Time-Varying Framework Using Kernels

To incorporate the time-varying coefficients, we extend the LC model as follows:(4)lnmx,t=ax+bx,tkt+εx,t,
such that the age-specific declines are allowed to be dynamic. This suggests that the relative age-specific mortality decline speed is now time-dependent. In terms of the forecasting, we have that
(5)lnm^x,T+h=a^x+b^x,T+hk^T+h,
where b^x,T+h is the forecast bx,t at step h, and k^T+h is identically defined as in Equation (3). Consequently, to obtain forecasts of this time-varying framework, one needs to additionally model and forecast the time-dependent bx,t. (Note that we do not require the assumption bx,t>0. Negative values mean that mortality rates at certain ages may (temporarily) increase (relative to other ages), rather than decline. As explained above, since this paper works with low-mortality populations, consistent declines are expected and more likely to occur.

For the estimation of the time-varying bx,t, many effective methods have been discussed in the statistics literature, including polynomial splines [20,21], smoothing splines [22,23], and kernel-local polynomial smoothing [24]. Among them, one of the most widely used methods is the kernel-local polynomial smoothing, which includes the local constant and the local linear estimation. In this paper, we illustrate our method using the local constant kernel smoothing method [7], also known as the Nadaraya–Watson estimator.

To implement the estimation, at each time t, the usual SVD will be applied once to Kb(τs−τ)lnmx,s, where s=1,2,...,T, τ=t/T and τs=s/T. The resulting estimated “weighted” age-specific declines will be the corresponding b^x,t. In addition, Kb(τs−τ) is a known kernel function with b known as the bandwidth, and Kb(τs−τ) is essentially a weight for the sth observation. For instance, with the widely employed Gaussian kernel, we have that
Kb(τs−τ)=12πbe−[(τs−τ)/b]22
which is essentially the Gaussian density evaluated at (τs−τ)/b and further scaled by b. The bandwidth b then determines the weights distributed to each observation when estimating bx,t. A larger b means weights are more evenly distributed. Other than the Gaussian kernel, we also examine the popular Epanechnikov kernel in this paper, which is specified as
Kb(τs−τ)=0.75b{1−[(τs−τ)/b]2}+. This kernel is also investigated in various mortality research, including Chang and Shi [19]. In this paper, we denote the time-varying coefficients LC model estimated by the Gaussian and Epanechnikov kernels as LC-G and LC-E, respectively.

We now employ the LC-E and LC-G models to revisit the mortality rates presented in Figure 1, and the resulting fitted b^x,t are plotted in Figure 3a,b, respectively. respectively. (The bandwidths are chosen in a similar manner as that described in Section 2.4.3. In short, we employ the same hold-out sample strategy for data spanning 1950–2019. Forecasts of the age-specific mortality declines (b^x,t) are produced using the exponential smoothing state space model discussed in Feng and Shi [27]. The bandwidths are then chosen as those minimize the forecasting errors of logged mortality rates in the hold-out sample). Both the fitted curves and time-varying patterns of the LC-E and LC-G models are similar to each other. Compared to the preliminary results displayed in Figure 1b with a running window, less randomness is observed. This may be explained by the fact that the entire (weighted) sample is used to produce each individual b^x,t. Roughly speaking, dynamics produced by kernels and the running window are consistent. However, despite that we do observe the rotation of b^x,t over most age groups as argued by Li et al. [5], the mortality declines at very old ages seem to decelerate rather than accelerate. Thus, an adjustment needs to be adopted before reliable mortality modelling and forecasting can be implemented with the dynamic b^x,t. Otherwise, the forecast mortality improvements at old ages may gradually decline, leading to a larger gap between mortality rates of relatively younger and older ages. This is contrary to the rotation proposed by Li et al. [5] and the concept of (age) coherence studied in the demographic and actuarial literature (see, for example, [6,9,28], among others).


<figure>
  <figcaption><strong>Figure 3</strong> Fitted age-specific declines b^x,t of the averaged population, 1950–2019: (a) Epanechnikov kernel; (b) Gaussian kernel.</figcaption>
</figure>


#### 2.4.2. Coherent Modelling of the Dynamic Age-Specific Mortality Declines

To adjust b^x,t, we require that forecast mortality rates across ages will not diverge in the long run. This idea, known as age coherence, is much in-line with the rotation argued in Li et al. [5] and is critical to producing biologically reasonable forecasts of mortality rates in the long-term analysis [6]. The age coherence is formally defined as follows.

To accommodate the age coherence in mortality forecasting, it is worth noting that lnmx,t is usually assumed to be a non-stationary I(1) process (see, for example, [6,19,28,29,30], among others). Thus, let yx,t=lnmx,t−lnmx,t−1, which is known as the mortality improvement of age x at time t, its long-run mean must be time-independent due to the stationarity. It can then be shown that
lnm^x,T+h=E(lnmx,T+h|ΩT)=lnmx,T+∑k=1hE(yx,T+k|ΩT)=Op(1)+hμ^x
when h goes large, where ΩT is the information set at time T. Thus, we have that
|lnm^i,T+h−lnm^j,T+h|=Op(1)+|h(μ^i−μ^j)|,
where μ^x is the fitted long-run mean of the stationary series yx,t. It can then be seen that the only scenario to ensure the age coherence is that μ^i≡μ^j for all i,j=1,...,N. From Equation (5), when h→∞, it is easy to see that y^x,T+h=b^x,T+hd, where d is identically defined as in Equation (2). Further, since yx,t is assumed stationary, the condition of μ^i≡μ^j is equivalent to b^i,T+h≡b^j,T+h for all i,j=1,...,N. With the constraint of the LC model, such that ∑xb^x,T+h=1, we require that b^x,T+h converges to 1/N for all x=1,...,N when h→∞.

We now discuss an appropriate model to study bx,t such that the age coherence of the forecast rates is ensured. Note that the condition all b^x,T+h converging to the same constant 1/N implies that bx,t−1/N is a stationary sequence with 0 mean for all x. Hence, we denote this sequence by bx,t*, an appropriate parametric structure analogous to that discussed in Li and Lu [6] and described below.
(6)b1,t*=α1b1,t−1*+ε1,tbb2,t*=α2b2,t−1*+β2b1,t−1*+ε2,tbbi,t*=αibi,t−1*+βibi−1,t−1*+γibi−2,t−1*+εi,tb
where i=3,...,N, and t=1,...,T. Essentially, Equation (6) is a vector autoregressive (VAR) model with constrained coefficient matrix. According to Li and Lu [6], the constraint is to emphasize the impact of the temporal effect (measured by αi) and those of the cohorts effect (measured by βi for the same cohort and γi for the nearest younger cohort). The forecasts of b^x,T+h* are produced in the same way as for a usual VAR model, based on which we can derive b^x,T+h=b^x,T+h*+1/N. It can be seen that as long as the VAR of Equation (6) is stationary (a sufficient condition would be that summations of absolute values of αi, βi, and γi are all smaller than or equal to 1 for all i=1,...,N), b^x,T+h* will converge to 0 for all x in the long run, and thus the forecast mortality rates will be age coherent. In addition, at each forecasting step, we can rescale b^x,T+h to sum up to 1 to satisfy the constraint ∑xb^x,T+h=1.

In terms of the estimation, Equation (6) can be solved using the penalized least squares (PLS), and its loss function is defined below:(7)LF=∑i=3N∑t=2T[bi,t*−αibi,t−1*−βibi−1,t−1*−γibi−2,t−1*]2+∑t=2T[b2,t*−α2b2,t−1*−β2b1,t−1*]+∑t=2T(b1,t*−α1b1,t−1*)2+λα∑i=2N(αi−αi−1)2+λβ∑i=3N(βi−βi−1)2+λγ∑i=4N(γi−γi−1)2,
where λα, λβ, and λγ are pre-selected smoothing parameters of αi, βi, and γi, respectively.


#### 2.4.3. Tuning Parameters Selection and the Estimation Procedure

The only outstanding issue now is how to select the tuning parameters, i.e., smoothing penalties of the time-varying coefficients LC models. In a usual case, a cross-validation technique can be employed to prevent the model from overfitting. It is worth noting that a usual cross-validation technique for time-series data, such as the expanding-window approach explained in Hyndman and Athanasopoulos [31], is not quite applicable in our case. The reason is that this expanding-window approach normally considers a very short forecasting step. In contrast, age-coherent adjustment of the LC model emphasizes the long-term forecast. Thus, we employ a hold-out-sample approach to select the tuning parameters (b and three λ’s), which minimizes
RMSFE=1N(T/3)∑i=1N∑h=1T/3lnm^i,2T/3+h−lnmi,2T/3+h2,
where RMSFE is the root of mean squared forecasting errors (since logged mortality rates are modeled, the RMSFE also considers the logged rather than original values. If an exponential transformation is applied, the predicted original mortality rates are unavoidably exposed to the famous Jensen’s inequality issue. Thus, the accuracy of forecasting is inherently lower than the logged rate is considered), and the evaluation period is given by the last third ([2T/3,T]) of the data in our study. (Note that the choice of the length of the test sample (one-third) is common among existing studies. Adopting other popular alternatives, such as the last fourth, fifth, and tenth sample will lead to robust results.)

In summary, forecasting with the LC-E and LC-G models can be implemented with the following steps:Fit the original LC model with the full sample to obtain a^x, k^T, and d;For the training sample spanning [1,2T/3−1], use the Epanechnikov (LC-E) or Gaussian (LC-G) kernel to obtain bx,t, based on which the constrained VAR model of Equation (6) is fitted for bx,t*;Select the optimal tuning parameters b, λα, λβ, and λγ via a grid search, such that the RMSFE of the test sample over [2T/3,T] is minimized;With the selected tuning parameters, fit the LC-E or LC-G model for the full sample;Forecast b^x,T+h with the fitted model, and then produce lnm^x,T+h with Equation (5), where a^x and k^T+h=k^T+hd sourced from Step 1.

To study the uncertainties of the forecast, the same procedure of the LC model can be applied for the LC-E and LC-G models proposed in this section. For instance, assuming that et in Equation (2) follows a Gaussian distribution, the prediction interval (PI) of the estimated life expectancies will be produced based on simulations. More specifically, we use method (I) described in Li [32] to implement the simulation, and a 95% PI is then comprises the 2.5th and 97.5th percentiles of the simulated results.



### 2.5. Related Mortality Models

Other than the three factors (ax, bx, and kt) used in the LC model, existing research has proposed alternative specifications to model mortality rates. For instance, Renshaw and Haberman [15], Cairns et al. [33], Renshaw and Haberman [34], and Plat [35] have considered additional factors, such as the cohort impacts and/or other temporal factors. Brouhns et al. [18], Currie et al. [36], Wang and Lu [37], and Debon et al. [38] calibrate mortality rates with different statistical methodologies. Machine learning techniques are considered in Hainaut [39], Levantesi and Pizzorusso [40], Nigri et al. [41], and Doukhan et al. [42]. Other studies, such as [43,44,45], introduce different time-series models to forecast the temporal patterns. Comprehensively reviewing those models is out of the scope of this paper, and please see specifications therein for details.



## 3. Results and Discussion

We model the mortality data and present the results in this section. As demonstrated in Figure 1, on average, the mortality rates consistently decline across all ages. This is also true for individual populations, as can be observed in Figure 4, where four countries are inspected for illustrative purposes. Despite the data volatility in some cases (e.g., Sweden, due to its small population size), substantial mortality improvements take place for both young and old ages. For instance, the “accidental hump” of ages 20–25 which was outstanding in the 1980s, has been flattening over time in all countries.


<figure>
  <figcaption><strong>Figure 4</strong> Mortality rates (lnmx,t) over 1950–2019:(a) Australia; (b) Canada; (c) Spain; (d) Sweden.</figcaption>
</figure>

Following the steps described in Section 2, we fit all models over the dataset 1950–2000 as the training set, and forecast mortality rates from 2000 to 2019 as the test set. The selected bandwidths are displayed in Table 1 for the LC-E and LC-G models. To ensure the validity of the VAR(1) model to study bx,t, the assumptions of stationarity and adequacy of VAR(1) need to be tested for the in-sample b^x,t. The I(0) feature is tested via the usual augmented Dickey–Fuller (ADF) unit root test, and the adequacy of VAR(1) is tested by the Granger causality (GC) test. Recall that for each population, we have a total of 101 age groups, and the bx,t is estimated in 2 sets via the LC-E and LC-G. All tests are performed at the 5% level, and the number out of 101 violated assumptions are presented in Table 1. It is clear that in the vast majority of cases, both the stationarity and model adequacy assumptions hold. The actual percentages of negative outcomes are close to expected (i.e., 5%). Those results validate the application of the VAR(1) framework for both the LC-E and LC-G models.

### 3.1. Out-of-Sample Forecasting Analysis

We firstly consider the forecasting performance of the proposed LC-E and LL-G models. In particular, we compare their out-of-sample forecasting accuracy with those of the LC and BMS models. Following Li and Lu [6], Feng et al. [28], and Chang and Shi [19], recall that the training sample is set to 1950–2000, and the test sample is 2001–2019. To measure the accuracy, the RMSFE is computed as follows, where the mortality data of each country are fitted into each of the four models individually:RMSFEh=1101×h∑i=1101∑s=1hlnm^i,2000+s−lnmi,2000+s2.

Thus, RMSFE19 is the overall forecasting accuracy measure covering the entire test period, whereas RMSFEh with 1≤h≤19 is the accumulated forecasting accuracy measure up to the hth step.

Our baseline results, including single-year age mortality rates over 1950–2019, are presented in Table 2. Overall, except for the UK data, the RMSFE19 of LC-E and LC-G are uniformly smaller than those of the LC model for all the examined populations. This suggests the improved forecasting performance considering the time-varying b^x,T+h. The BMS model, with adjustments on both shortened training sample period and estimation of kt, improves the forecasting accuracy of LC in seven countries. Despite this, except for the UK, Japan, the Netherlands and the USA, both the LC-E and LC-G models consistently outperforms the BMS counterparty in 13 cases. This suggests that appropriately allowing for dynamic age-specific mortality declines is more effective than the two adjustments in BMS to improve the forecasting accuracy. Although the LC-E model outperforms LC-G in six cases, the differences between the two approaches are marginal. This indicates that the forecasting performance of the time-varying coefficients framework described in Section 2.4 is robust against specific kernel functions. Finally, the RMSFE19 averaged over the fifteen countries of the LC, BMS, LC-E, and LC-G models are 0.2576, 0.2610, 0.2202, and 0.2197, respectively. Thus, on average, BMS cannot improve the forecasting performance of LC, whereas the LC-E and LC-G models can improve it by 14.7%. From a statistical point of view, if an unknown population is randomly chosen, we expected that LC-E or LC-G is more likely to improve the out-of-sample forecasting, with the forecasting error expected to be reduced by roughly 15%.

To gain more insights of the four models’ performances at different horizons, we plot the RMSFEh at each of the sixteen forecasting steps. For demonstration purposes, those of Australia, Canada, Spain, and Sweden are presented in Figure 5. Results of other countries are available upon request. In the vast majority of cases, we see that the RMSFEs of the LC-E and LC-G models are smaller than those of the other two models. This indicates that LC-G and LC-H are able to generate relatively more accurate forecasting results at different horizons.


<figure>
  <figcaption><strong>Figure 5</strong> RMSFE over forecasting steps: (a) Australia; (b) Canada; (c) Spain; (d) Sweden.</figcaption>
</figure>

We now evaluate the robustness of the forecasting results by performing the out-of-sample forecasting analysis under two major variant settings: (1) we follow Li et al. [5] and model the logged mortality rates of the five-year ages instead of the single-year groups; and (2) we consider a shorter training sample over 1970–2000 to avoid fluctuations in 1950–1969 for certain populations (e.g., Spain). A summary of the RMSFE19 across the 15 countries is reported in Table 3. Overall, we conclude that both LC-E and LC-G are able to produce satisfying forecasting performances that are robust across different settings. In addition, using different kernel functions in the time-varying framework only leads to marginal differences in the out-of-sample forecasts.


### 3.2. Long-Term Analyses: 2020–2100

We now conduct long-term analyses beyond the full sample period using the proposed time-varying LC models. Since the produced forecasts are robust against the selected kernels, it is sufficient to focus on one model only. More specifically, we follow the steps described in Section 2.4.3 to fit the LC-G model using the full sample (1950–2019) and produce b^x,T+h over 2020–2100. We report the forecasts for Australia, Canada, Spain, and Sweden in Figure 6. Overall, all b^x,T+h are converging to the long-run mean 1/101. In other words, all the curves are “rotating” to a flat horizontal line. The dynamics are consistent with those of Li et al. [5] (see, for example, Figure 5), with younger ages faster and older ages slower. Unlike in Li et al. [5], the speed of rotation is data-driven for the LC-G model and does not suffer the potential ad hoc issue when determined by expert judgment [6]. It is worth mentioning that the impact of the so-called “accident hump” is more obvious for the Australian population, since b^25,T+h is lower than b^x,T+h of the neighboring ages. Such a difference, however, is much smaller when it is closer to the end of the forecasting period (2100).


<figure>
  <figcaption><strong>Figure 6</strong> Projected rotation of age-specific mortality decline (b^x,T+h), 2020–2100: (a) Australia; (b) Canada; (c) Spain; (d) Sweden.</figcaption>
</figure>

Using those obtained b^x,T+h, we can derive forecast mortality rates and thus produce the life expectancy using the LC-G model. Since life expectancy at birth (e0) considers mortality rates at all ages, we contrast the forecast e^0 of LC-G and LC over 2020–2100. Both the point and interval forecasts of Australia, Canada, Spain, and Sweden are plotted in Figure 7. It can be seen that e^0 generated by LC-G are uniformly larger than those of the LC model. This is consistent with the fact that the LC-G model implements a rotation [5] of b^x, and with the argued age-coherent property of the forecast mortality rates in the long run [6]. In addition, despite the PIs of LC-G being slightly wider than those of LC, their widths are at similar levels. This may be explained by the fact that k^T+h are identical for both models. As of 2100, the point forecast e^0 of LC-G has exceeded the upper bound of the 95% PI of LC for all countries except Australia, implying a significant difference. More specifically, the point forecast e^0 of LC-G (LC) for Australia, Canada, Spain, and Sweden grow from 83.4, 82.9, 82.9, and 82.7, respectively, in 2020 to 94.4, 94.3, 94.9, and 94.6 (92.3, 91.8, 91.9, and 90.1), respectively, in 2100.


<figure>
  <figcaption><strong>Figure 7</strong> Forecast e0 over 2020–2100, single-population models: (a) Australia; (b) Canada; (c) Spain; (d) Sweden.</figcaption>
</figure>

To analyze the reasons contributing to those deviations in e^0 of LC and LC-G in 2100, ranging from 2.1 (Australia) to 4.5 (Sweden) years, we plot the forecast logged mortality rates in Figure 8. Comparing with the true rates in 2019, it is observed that little improvements are gained at old ages for the forecasts produced by the LC model. In contrast, due to the rotation and age-coherent property, forecasts produced by LC-G demonstrate much more obvious mortality improvements at old ages. In addition, since b^x,T+h sum up to one at each step h, less mortality declines are distributed to the young ages. This contributes to the rotation-like difference when contrasting the lnm^x,T+h produced by LC-G to those by LC. Overall, the difference in e^0 produced by LC and LC-G, as presented in Figure 7, may be explained by the potentially large impacts of mortality rates at old ages in the calculation of life expectancy. Nevertheless, due to the influence of the smoothing penalties in (7), the long-run forecast logged mortality rates of LC-G are much smoother than those of the LC model.


<figure>
  <figcaption><strong>Figure 8</strong> Forecast lnmx,t over 2020–2100: (a) Australia; (b) Canada; (c) Spain; (d) Sweden.</figcaption>
</figure>



## 4. Extensions to the Multi-Population Modelling: An Illustrative Example

A multi-population extension of the LC model is studied in the seminal work of Li and Lee [9]. An additional common factor which controls the relationships between populations is included in the proposed Li–Lee (LL) model. Specifically, the logged mortality rate is modeled as:(8)lnmx,t,j=ax,j+BxKt+bx,jkt,j+εx,t,j,
where ax,j represents the average of the age-specific mortality level for the jth population, Bx and Kt represent the age effect and period effect of the common factor, kt,j is the time component of the ith population with age response bx,j, and εx,t,j is the population-specific error term. The common factor BxKt describes the mortality trend of all modeled populations. To obtain the estimates, in this paper, we follow Li and Lee [9] to apply a usual LC model to the logged mortality rates averaged over all the fifteen populations. Consistent with LC, a^x,j is the average of lnmx,t,j over t. The population-specific factor bx,ikt,i can be estimated by applying SVD to the residual matrix (lnmx,t,j−a^x,j−B^xK^t).

Similar to the case under LC, the common mortality index Kt is assumed non-stationary and can be modeled as a random walk with drift process. In contrast, the group-specific time component kt,i is fitted by a stationary autoregressive process (set to AR(1) in this paper, as considered in Li and Lee [9]), such that long-term forecasts are coherent (i.e., non-divergent) across the included populations. Given the data observed in the last year T, the h-step-ahead forecast of the logged mortality rate is given as follows:(9)lnm^x,T+h,j=a^x,j+B^xK^T+h+b^x,jk^T+h,j.

Despite its desirable coherence among populations, lnm^x,T+h,j of the LL model is still not age coherent. To see this, without identical B^x across ages, the non-stationary temporal term K^T+h in Equation (9) can lead to divergent long-run forecasts even for neighboring ages of the same population.

The multi-population extensions of the BMS, LC-E, and LC-G are straightforward to derive. Essentially, instead of fitting an LC model to forecast the common trend B^xK^T+h, BMS, LC-E, and LC-G models can be fitted for the averaged rates. Consequently, forecasts of their multi-population extensions can be produced below.
(10)lnm^x,T+h,jB=a^x,j+B^xK^T+hB+b^x,jk^T+h,jlnm^x,T+h,jE=a^x,j+B^x,T+hEK^T+h+b^x,jk^T+h,jlnm^x,T+h,jG=a^x,j+B^x,T+hGK^T+h+b^x,jk^T+h,j
where the superscripts B, E, and G indicate the forecast of the multi-population extension of the BMS (LL-BMS), LC-E (LL-E), and LC-G (LL-G), respectively. It can be seen that in all cases, the population-specific average rate a^x,j and stationary trend b^x,jk^T+h,j are unchanged from that of the LL model. For the LL-BMS, the same two adjustments, selecting an optimal sample period and using a Poisson model to obtain K^T+hB, as considered in the single-population BMS model are adopted for the averaged population. For the LL-E and LL-G models, B^x,T+hE and B^x,T+hG will be forecast using the constrained VAR model as for the single-population case described in Equation (6), based on the averaged population. The tuning parameters will be selected in the same way as described in Section 2.4.3, which will minimize the RMSFE of the averaged population for the hold-out sample.

Without imposing a long-run restriction, LL-BMS will lead to population-coherent forecasts as the LL, which are, however, not age coherent when h→∞. In contrast, following the discussions in Section 2.4, B^x,T+hE and B^x,T+hG are age invariant in the long run. Since k^T+h,j is a stationary process, b^x,jk^T+h,j will converge to a constant for all ages. Thus, the logged mortality rates forecast by LL-E and LL-G are both age- and population-coherent in the long run across all ages and populations.

For illustration purposes, we consider the baseline results only as in Section 3.1 and Section 3.2 for the multi-population models. The RMSFE19 of the out-of-sample forecasts for each population are reported in Table 4. First, contrasting the results of Table 2 and Table 4, it is worth noting that in 10, 12, 8, and 9 out of the 15 countries, respectively, the forecasting performances of the LL, LL-BMS, LL-E, and LL-G are superior to those of the corresponding single-population counterparties. Second, LL-E and LL-G outperform the LL model in all the 15 populations. Compared to the LL-BMS model, LL-G and LL-H lead to more accurate forecasts in 11 cases. Finally, although LL-G beats LL-E in all cases except for Japan, the differences between the two time-varying models are still marginal in most cases. On average, LL-E and LL-G improve the forecasting performance of the LL by 9.1% and 11.3%, respectively. Thus, those results are very consistent with the single-population out-of-sample forecasting metrics, suggesting that allowing for dynamic age-specific mortality declines can produce the best-performing forecasts in the multi-population case.

We now examine the forecast life expectancy at birth over 2020–2100. In Figure 9, for the datasets of Australia, Canada, Spain, and Sweden, we present the point forecasts together with the 95% PIs produced by the LL and LL-G models. Consistent with Figure 7, the e^0 generated by LL-G are uniformly larger than those by the LL. This can still be explained by the desirable age-coherence property of the LL-G model. In addition, all point forecasts of the LL-G model are above the corresponding upper bounds of the 95% PIs of the LC counterparty, suggesting a significant difference. Nevertheless, due to the population coherence, LL leads to similar forecasts of e0 in 2100, ranging from 91.2 (Sweden) to 91.8 (Australia). For the same reason, the forecast e0 in 2100 are also close to each other for the LL-G model, which vary from 93.0 (Sweden) to 94.8 (Canada). Nevertheless, for both the LL and LL-H models, the widths of the resulting PIs are narrower than those observed in Figure 7 for the single-population models. This can be attributed to the fact that more information is used in the multi-population framework, which can therefore reduce the uncertainty of the unexplained random disturbances.


<figure>
  <figcaption><strong>Figure 9</strong> Forecast e0 over 2020–2100, Multi-population models: (a) Australia; (b) Canada; (c) Spain; (d) Sweden.</figcaption>
</figure>


## 5. Concluding Remarks

This paper investigates a time-varying coefficients extension of the Lee–Carter (LC) model. As argued in the influential work of Li et al. [5], mortality declines decelerate at young ages and accelerate at old ages. The lack of considering such dynamics makes the LC model less accurate in forecasting mortality rates in the long-term analysis.

To effectively resolve this issue without imposing computationally intensive burdens, we employ the kernel time-varying parametric approach as examined in a recent work of Chang and Shi [19]. Specifically, in-sample time-dependent bx,t are first estimated using the Epanechnikov (LC-E) and Gaussian (LC-G) kernel methods. To project the out-of-sample b^x,T+h, a VAR-type model similar to that considered in Li and Lu [6] is further adopted. The forecasting of logged mortality rates is therefore conducted analogously to that for the LC model. For the proposed LC-E and LC-G models, we can draw five key conclusions in this paper. First, the long-run age-specific patterns of mortality declines are forced (asymptotically) identical across all ages. This ensures the desirable age coherence as proposed in the recent literature [6,19,28,29]. Second, the LC-E and LC-G models are computationally efficient and data-driven. Specifically, both models adopt the penalized least square, which results in closed-form solutions. In addition, the parameters and smoothing penalties relevant to the speeds of rotation in b^x,T+h are estimated/determined in a data-driven fashion, which is different from the ad hoc judgment of the rotation used in Li et al. [5]. Thirdly, using a large sample of uni-sex data of 15 countries over 1950–2019, we demonstrate the outstanding out-of-sample forecasting performance of the LC-E and LC-G models. The differences in the selection of the kernel function is deemed marginal. This conclusion is robust when a five-year instead of a one-year age mortality rate is modeled, and the training period is shortened to 1970–2000. Therefore, we recommend modelling and forecasting mortality rates with the time-varying coefficients LC model in demographic practices. Fourthly, our long-term analysis supports the effectiveness of the age-coherent forecasts produced by the recommended model. When forecast to 2100, significantly longer life expectancies at birth are generated by the LC-G model in most illustrated cases, which may be caused by its larger forecast mortality improvements at old ages. Finally, multi-population extensions of the LC-E (LL-E) and LC-G (LL-G) are straightforward to derive, which are based on the specification of the Li–Lee (LL) model Li and Lu [9]. On one hand, our proposed extension can achieve coherence across both ages and populations, whereas LL can only forecast non-divergent mortality rates across populations. On the other hand, consistent conclusions hold as those in the single-population scenario. Such conclusions include the more accurate out-of-sample forecasts and larger long-range projections of life expectancies led by the LL-G than the LL model.

There are some directions that are worth examining for future research. First, it is of interest to investigate female and male populations separately. For each country, differences between the selected tuning parameters of the LC-E and LC-G models may indicate important variations of the short-term speeds of mortality rotations for the two sexes. In addition, recent studies, including Vekas [46], have outlined that the rotation proposed by Li et al. [5] is notably more prevalent in populations of women than among men. This strongly motivates the exploration of sex differences using LC-E and LC-G models. Secondly, the fitted d in modelling the temporal patterns of kt may be made further time-dependent. Third, it is worth exploring the applicability of our specification to alternative models as listed in Section 2.5. For factor-based models, such as Renshaw and Haberman [34], our time-varying specification may be straightforwardly extensible. It will be more challenging to incorporate dynamics in other frameworks. Fourth, in the multi-population case, we may allow the population-specific bx,i to be dynamic in the forecasting steps. This more flexible specification might further improve the forecasting accuracy and provide additional information on the population-specific rotation of the bx,i. Finally, impacts of COVID-19 may have significantly delayed mortality declines, especially for the old ages. After more data become available, our kernel-based models can be used to study how such shocks evolve and whether they are short-lived (and if so, when they eventually die out).


## References

1. MaestasN.
MullenK.J.
PowellD.
The Effect of Population Aging on Economic Growth, the Labor Force and ProductivityTechnical reportNational Bureau of Economic ResearchCambridge, MA, USA2016

2. FentonJ.J.
JerantA.F.
BertakisK.D.
FranksP.
The cost of satisfaction: A national study of patient satisfaction, health care utilization, expenditures, and mortalityArch. Intern. Med.201217240541110.1001/archinternmed.2011.166222331982

3. HuangW.
ZhangC.
The power of social pensions: Evidence from China’s new rural pension schemeAm. Econ. J. Appl. Econ.20211317920510.1257/app.20170789

4. LeeR.D.
CarterL.R.
Modeling and forecasting US mortalityJ. Am. Stat. Assoc.199287659671

5. LiN.
LeeR.
GerlandP.
Extending the Lee–Carter method to model the rotation of age patterns of mortality decline for long-term projectionsDemography2013502037205110.1007/s13524-013-0232-223904392PMC4550589

6. LiH.
LuY.
Coherent Forecasting of Mortality Rates: A Sparse Vector-Autoregression ApproachASTIN Bull. J. IAA20174756360010.1017/asb.2016.37

7. FanJ.
GijbelsI.
Local Polynomial Modelling and Its Applications: Monographs on Statistics and Applied ProbabilityCRC PressBoca Raton, FL, USA1996Volume 66

8. Human Mortality Database
University of California, Berkeley (USA), and Max Planck Institute for Demographic Research (Germany)2023Available online: https://www.mortality.org/(accessed on 28 January 2023)

9. LiN.
LeeR.
Coherent mortality forecasts for a group of populations: An extension of the Lee–Carter methodDemography20054257559410.1353/dem.2005.002116235614PMC1356525

10. BoothH.
HyndmanR.
TickleL.
De JongP.
Lee–Carter mortality forecasting: A multi-country comparison of variants and extensionsDemogr. Res.20061528931010.4054/DemRes.2006.15.9

11. LiH.
LiJ.S.H.
Optimizing the Lee–Carter approach in the presence of structural changes in time and age patterns of mortality improvementsDemography2017541073109510.1007/s13524-017-0579-x28523453

12. BoonenT.J.
LiH.
Modeling and forecasting mortality with economic growth: A multipopulation approachDemography2017541921194610.1007/s13524-017-0610-228948542

13. LiH.
ShiY.
Forecasting mortality with international linkages: A global vector-autoregression approachInsur. Math. Econ.2021100597510.1016/j.insmatheco.2021.04.006

14. LiH.
ShiY.
Mortality forecasting with an age-coherent sparse var modelRisks202193510.3390/risks9020035

15. RenshawA.E.
HabermanS.
Lee–Carter mortality forecasting with age-specific enhancementInsur. Math. Econ.20033325527210.1016/S0167-6687(03)00138-0

16. LiH.
De WaegenaereA.
MelenbergB.
The choice of sample size for mortality forecasting: A Bayesian learning approachInsur. Math. Econ.20156315316810.1016/j.insmatheco.2015.03.024

17. BoothH.
MaindonaldJ.
SmithL.
Applying Lee–Carter under conditions of variable mortality declinePopul. Stud.20025632533610.1080/0032472021593512553330

18. BrouhnsN.
DenuitM.
VermuntJ.K.
A Poisson log-bilinear regression approach to the construction of projected lifetablesInsur. Math. Econ.20023137339310.1016/S0167-6687(02)00185-3

19. ChangL.
ShiY.
Dynamic modelling and coherent forecasting of mortality rates: A time-varying coefficient spatial-temporal autoregressive approachScand. Actuar. J.202084386310.1080/03461238.2020.1773523

20. HuangJ.Z.
WuC.O.
ZhouL.
Polynomial spline estimation and inference for varying coefficient models with longitudinal dataStat. Sin.200414763788

21. HuangJ.Z.
ShenH.
Functional coefficient regression models for non-linear time series: A polynomial spline approachScand. J. Stat.20043151553410.1111/j.1467-9469.2004.00404.x

22. HastieT.
TibshiraniR.
Varying-coefficient modelsJ. R. Stat. Soc. Ser. B Methodol.19935575777910.1111/j.2517-6161.1993.tb01939.x

23. ChiangC.T.
RiceJ.A.
WuC.O.
Smoothing spline estimation for varying coefficient models with repeatedly measured dependent variablesJ. Am. Stat. Assoc.20019660561910.1198/016214501753168280

24. FanJ.
ZhangW.
Statistical estimation in varying coefficient modelsAnn. Stat.1999271491151810.1214/aos/1017939139

25. WandM.P.
JonesM.C.
Kernel SmoothingCRC PressBoca Raton, FL, USA1994

26. TheodoridisS.
Machine Learning: A Bayesian and Optimization PerspectiveAcademic PressCambridge, MA, USA2015

27. FengL.
ShiY.
Forecasting mortality rates: Multivariate or univariate models?J. Popul. Res.20183528931810.1007/s12546-018-9205-z

28. FengL.
ShiY.
ChangL.
Forecasting mortality with a hyperbolic spatial temporal VAR modelInt. J. Forecast.20203725527310.1016/j.ijforecast.2020.05.003

29. LiH.
LuY.
LyuP.
Coherent mortality forecasting for less developed countriesRisks2021915110.3390/risks9090151

30. GuibertQ.
LopezO.
PietteP.
Forecasting mortality rate improvements with a high-dimensional VARInsur. Math. Econ.20198825527210.1016/j.insmatheco.2019.07.004

31. HyndmanR.J.
AthanasopoulosG.
Forecasting: Principles and PracticeOTextsMelbourne, Australia2018

32. LiJ.
A quantitative comparison of simulation strategies for mortality projectionAnn. Actuar. Sci.2014828110.1017/S1748499514000153

33. CairnsA.J.
BlakeD.
DowdK.
A two-factor model for stochastic mortality with parameter uncertainty: Theory and calibrationJ. Risk Insur.20067368771810.1111/j.1539-6975.2006.00195.x

34. RenshawA.E.
HabermanS.
A cohort-based extension to the Lee–Carter model for mortality reduction factorsInsur. Math. Econ.20063855657010.1016/j.insmatheco.2005.12.001

35. PlatR.
On stochastic mortality modelingInsur. Math. Econ.20094539340410.1016/j.insmatheco.2009.08.006

36. CurrieI.D.
DurbanM.
EilersP.H.
Smoothing and forecasting mortality ratesStat. Model.2004427929810.1191/1471082X04st080oa

37. WangD.
LuP.
Modelling and forecasting mortality distributions in England and Wales using the Lee–Carter modelJ. Appl. Stat.20053287388510.1080/02664760500163441

38. DebónA.
MontesF.
MateuJ.
PorcuE.
BevilacquaM.
Modelling residuals dependence in dynamic life tables: A geostatistical approachComput. Stat. Data Anal.2008523128314710.1016/j.csda.2007.08.006

39. HainautD.
A neural-network analyzer for mortality forecastASTIN Bull. J. IAA20184848150810.1017/asb.2017.45

40. LevantesiS.
PizzorussoV.
Application of machine learning to mortality modeling and forecastingRisks201972610.3390/risks7010026

41. NigriA.
LevantesiS.
MarinoM.
ScognamiglioS.
PerlaF.
A deep learning integrated Lee–Carter modelRisks201973310.3390/risks7010033

42. RichmanR.
WüthrichM.V.
A neural network extension of the Lee–Carter model to multiple populationsAnn. Actuar. Sci.20211534636610.1017/S1748499519000071

43. HabermanS.
RenshawA.
A comparative study of parametric mortality projection modelsInsur. Math. Econ.201148355510.1016/j.insmatheco.2010.09.003

44. CadenaM.
Mortality Models based on the Transform ∖log (-∖log x)arXiv20151502.07199

45. DoukhanP.
PommeretD.
RynkiewiczJ.
SalhiY.
A class of random field memory models for mortality forecastingInsur. Math. Econ.2017779711010.1016/j.insmatheco.2017.08.010

46. VékásP.
Rotation of the age pattern of mortality improvements in the European UnionCent. Eur. J. Oper. Res.2020281031104810.1007/s10100-019-00617-0
