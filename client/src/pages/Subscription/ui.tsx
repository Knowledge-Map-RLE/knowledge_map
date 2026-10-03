import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Header from '../../widgets/Header';
import styles from './Subscription.module.css';
import {
    PLANS,
    GROUPS,
    FAQ,
    FORUM_URL,
    type Plan,
} from './model';
import { useToast } from '../../shared/ui/Toast';
import {
    createCheckout,
    fetchSubscription,
    type SubscriptionState,
} from '../../services/api/billing';

const SubscriptionUI: React.FC = () => {
    const { t, i18n } = useTranslation();
    const localize = (key: string, russianSource: string) =>
        i18n.resolvedLanguage === 'ru' ? russianSource : t(key);
    const { error: toastError } = useToast();
    const [openFaq, setOpenFaq] = useState<number | null>(0);
    const [subscription, setSubscription] = useState<SubscriptionState | null>(null);
    const [checkoutPlan, setCheckoutPlan] = useState<string | null>(null);

    const loadSubscription = useCallback(async () => {
        try {
            const state = await fetchSubscription();
            setSubscription(state);
        } catch (err) {
            const message = err instanceof Error ? err.message : t('subscription.errors.status');
            if (!/401|Authorization|Unauthorized/i.test(message)) {
                toastError(message);
            }
            setSubscription(null);
        }
    }, [toastError, t]);

    useEffect(() => {
        loadSubscription();
    }, [loadSubscription]);

    const handleCheckout = useCallback(async (plan: Plan) => {
        if (plan.id === 'free') {
            return;
        }
        setCheckoutPlan(plan.id);
        try {
            const result = await createCheckout(plan.id.toUpperCase());
            if (result.confirmation_url) {
                window.location.href = result.confirmation_url;
                return;
            }
            throw new Error(t('subscription.errors.checkoutUrl'));
        } catch (err) {
            const message = err instanceof Error ? err.message : t('subscription.errors.purchase');
            if (!/401|Authorization|Unauthorized/i.test(message)) {
                toastError(message);
            }
        } finally {
            setCheckoutPlan(null);
        }
    }, [toastError, t]);

    const currentPlanCode = subscription?.plan_code ?? 'FREE';

    return (
        <div className={styles.page}>
            <Header showSearch={true} className={styles.header} />
            <main className={styles.main}>

                <section className={styles.pricing} id="pricing">
                    <div className={styles.pricingGlowBlue} />
                    <div className={styles.pricingGlowPurple} />
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                            <div className={styles.heroBadge}>{localize('subscription.hero.badge', 'Токены')}</div>
                            <h1 className={styles.sectionTitle}>{localize('subscription.hero.title', 'Пакеты токенов Карты Знаний')}</h1>
                            <p className={styles.sectionSubtitle}>
                                {localize('subscription.hero.description', 'Покупайте токены — платите только за использование. Сервис не потратит лишних денег: при исчерпании токенов ИИ-функции приостанавливаются.')}
                            </p>
                        </div>

                        <div className={styles.planGrid}>
                            {PLANS.map(plan => (
                                <PlanCard
                                    key={plan.id}
                                    plan={plan}
                                    current={plan.id.toUpperCase() === currentPlanCode}
                                    busy={checkoutPlan === plan.id}
                                    disabled={plan.id === 'free' && currentPlanCode === 'FREE'}
                                    onSelect={() => handleCheckout(plan)}
                                />
                            ))}
                        </div>
                    </div>
                </section>

                <section className={styles.comparison}>
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                            <h2 className={styles.sectionTitle}>{localize('subscription.comparison.title', 'Сравнение планов')}</h2>
                            <div className={styles.titleBar} />
                        </div>

                        <div className={styles.tableWrap}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th className={styles.thFeature}>{localize('subscription.comparison.feature', 'Функция')}</th>
                                        {PLANS.map(plan => (
                                            <th key={plan.id} className={`${styles.thPlan} ${plan.highlight ? styles.thPlanHighlight : ''}`}>
                                                <span className={styles.thPlanName}>{localize(`subscription.plans.${plan.id}.name`, plan.name)}</span>
                                                <span className={styles.thPlanPrice}>{plan.price}</span>
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {GROUPS.map((group, index) => (
                                        <GroupBody key={group.title} title={localize(`subscription.comparison.groups.${index}`, group.title)} groupId={`group-${index}`} rows={group.rows} />
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </section>

                <section className={styles.faq} id="faq">
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                            <h2 className={styles.sectionTitle}>{localize('subscription.faq.title', 'Частые вопросы')}</h2>
                        </div>
                        <div className={styles.faqList}>
                            {FAQ.map((item, index) => (
                                <div key={index} className={`${styles.faqItem} ${openFaq === index ? styles.faqItemOpen : ''}`}>
                                    <button
                                        type="button"
                                        className={styles.faqQuestion}
                                        onClick={() => setOpenFaq(openFaq === index ? null : index)}
                                    >
                                        <span>{localize(`subscription.faq.items.${index}.question`, item.question)}</span>
                                        <span className={styles.faqToggle}>+</span>
                                    </button>
                                    {openFaq === index && (
                                        <div className={styles.faqAnswer}>{localize(`subscription.faq.items.${index}.answer`, item.answer)}</div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                <section className={styles.cta}>
                    <div className={styles.ctaInner}>
                        <h2>{localize('subscription.callToAction.title', 'Поддержите науку о продлении жизни')}</h2>
                        <p>
                            {localize('subscription.callToAction.description', 'Проект открыт и бесплатен для всех. Купите пакет токенов — и вы получите полный набор ИИ-инструментов, а проект — устойчивость и развитие.')}
                        </p>
                        <div className={styles.ctaButtons}>
                            <button
                                type="button"
                                className={styles.ctaPrimaryBtn}
                                onClick={() => handleCheckout(PLANS[1])}
                                disabled={checkoutPlan !== null}
                            >
                                {checkoutPlan === PLANS[1].id ? localize('subscription.callToAction.redirecting', 'Перенаправляем…') : localize('subscription.callToAction.buyTokens', 'Купить токены')}
                            </button>
                            <a href={FORUM_URL} target="_blank" rel="noopener noreferrer" className={styles.ctaGhostBtn}>
                                {localize('subscription.callToAction.askCommunity', 'Задать вопрос в сообществе')}
                            </a>
                        </div>
                    </div>
                </section>

            </main>
        </div>
    );
};

const PlanCard: React.FC<{
    plan: Plan;
    current: boolean;
    busy: boolean;
    disabled: boolean;
    onSelect: () => void;
}> = ({ plan, current, busy, disabled, onSelect }) => {
    const { t, i18n } = useTranslation();
    const localize = (key: string, russianSource: string) =>
        i18n.resolvedLanguage === 'ru' ? russianSource : t(key);
    return (
    <div className={`${styles.planCard} ${plan.highlight ? styles.planCardHighlight : ''}`}>
        {plan.badge && <div className={styles.planBadge}>{localize(`subscription.plans.${plan.id}.badge`, plan.badge)}</div>}
        <h3 className={styles.planName}>{localize(`subscription.plans.${plan.id}.name`, plan.name)}</h3>
        <div className={styles.planPrice}>{plan.price}</div>
        <div className={styles.planPriceNote}>{localize(`subscription.plans.${plan.id}.priceNote`, plan.priceNote)}</div>
        <p className={styles.planDescription}>{localize(`subscription.plans.${plan.id}.description`, plan.description)}</p>
        <button
            type="button"
            className={styles.planButton}
            onClick={onSelect}
            disabled={busy || disabled}
        >
            {busy ? localize('subscription.callToAction.redirecting', 'Перенаправляем…') : current ? localize('subscription.plans.current', 'Текущий баланс') : localize(`subscription.plans.${plan.id}.ctaLabel`, plan.ctaLabel)}
        </button>
    </div>
    );
};

const GroupBody: React.FC<{
    title: string;
    groupId: string;
    rows: readonly { id: string; label: string; translationKey: string; free: boolean; paid: boolean }[];
}> = ({ title, groupId, rows }) => {
    const { t, i18n } = useTranslation();
    return (
      <>
        <tr className={styles.groupRow}>
            <td className={styles.groupTitle} colSpan={3}>{title}</td>
        </tr>
        {rows.map(row => (
            <tr key={groupId + '-' + row.label}>
                <td className={styles.featureName}>{i18n.resolvedLanguage === 'ru' ? row.label : t(row.translationKey)}</td>
                <td className={styles.featureCell}>{row.free ? <Check /> : <Dash />}</td>
                <td className={styles.featureCell}>{row.paid ? <Check /> : <Dash />}</td>
            </tr>
        ))}
      </>
    );
};

const Check: React.FC = () => (
    <span className={styles.check} aria-hidden="true">✓</span>
);

const Dash: React.FC = () => (
    <span className={styles.dash} aria-hidden="true">—</span>
);

export default SubscriptionUI;
