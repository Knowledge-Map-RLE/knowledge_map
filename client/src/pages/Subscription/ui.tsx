import { useCallback, useEffect, useState } from 'react';
import Header from '../../widgets/Header';
import styles from './Subscription.module.css';
import {
    PLANS,
    GROUPS,
    FAQ,
    FORUM_URL,
    type Plan,
} from './model';
import {
    cancelSubscription,
    createCheckout,
    fetchSubscription,
    type SubscriptionState,
} from '../../services/api/billing';

const SubscriptionUI: React.FC = () => {
    const [openFaq, setOpenFaq] = useState<number | null>(0);
    const [subscription, setSubscription] = useState<SubscriptionState | null>(null);
    const [subLoaded, setSubLoaded] = useState(false);
    const [subError, setSubError] = useState<string | null>(null);
    const [checkoutPlan, setCheckoutPlan] = useState<string | null>(null);
    const [checkoutError, setCheckoutError] = useState<string | null>(null);

    const loadSubscription = useCallback(async () => {
        try {
            const state = await fetchSubscription();
            setSubscription(state);
            setSubError(null);
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Не удалось получить статус подписки';
            if (!/401/.test(message)) {
                setSubError(message);
            }
            setSubscription(null);
        } finally {
            setSubLoaded(true);
        }
    }, []);

    useEffect(() => {
        loadSubscription();
    }, [loadSubscription]);

    const handleCheckout = useCallback(async (plan: Plan) => {
        if (plan.id === 'free') {
            return;
        }
        setCheckoutPlan(plan.id);
        setCheckoutError(null);
        try {
            const result = await createCheckout(plan.id.toUpperCase());
            if (result.confirmation_url) {
                window.location.href = result.confirmation_url;
                return;
            }
            throw new Error('Сервис не вернул ссылку на оплату');
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Не удалось оформить подписку';
            setCheckoutError(message);
        } finally {
            setCheckoutPlan(null);
        }
    }, []);

    const handleCancel = useCallback(async () => {
        try {
            await cancelSubscription();
            await loadSubscription();
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Не удалось отменить подписку';
            setSubError(message);
        }
    }, [loadSubscription]);

    const currentPlanCode = subscription?.plan_code ?? 'FREE';

    return (
        <div className={styles.page}>
            <Header showSearch={true} className={styles.header} />
            <main className={styles.main}>

                <section className={styles.statusSection}>
                    <div className={styles.sectionInner}>
                        {subLoaded && subscription && (
                            <div className={styles.statusBanner}>
                                <div className={styles.statusInfo}>
                                    <span className={styles.statusLabel}>Ваш тариф</span>
                                    <span className={styles.statusPlan}>{subscription.plan_code}</span>
                                    {subscription.cancel_at_period_end && (
                                        <span className={styles.statusCancelNote}>
                                            отменена, действует до конца периода
                                        </span>
                                    )}
                                </div>
                                <div className={styles.statusCredits}>
                                    <span className={styles.statusCreditsValue}>
                                        {subscription.credits.balance.toLocaleString('ru-RU')}
                                    </span>
                                    <span className={styles.statusCreditsLabel}>кредитов</span>
                                </div>
                                {subscription.active && !subscription.cancel_at_period_end && (
                                    <button
                                        type="button"
                                        className={styles.statusCancelBtn}
                                        onClick={handleCancel}
                                    >
                                        Отменить
                                    </button>
                                )}
                            </div>
                        )}
                        {subError && (
                            <div className={styles.statusError}>{subError}</div>
                        )}
                        {checkoutError && (
                            <div className={styles.statusError}>{checkoutError}</div>
                        )}
                    </div>
                </section>

                <section className={styles.pricing} id="pricing">
                    <div className={styles.pricingGlowBlue} />
                    <div className={styles.pricingGlowPurple} />
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                            <div className={styles.heroBadge}>Подписки</div>
                            <h1 className={styles.sectionTitle}>Тарифы Карты Знаний</h1>
                            <p className={styles.sectionSubtitle}>
                                Начните бесплатно и расширяйте возможности по мере роста.
                                Платные функции подключаются в один клик, ваши данные сохраняются при любом плане.
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
                            <h2 className={styles.sectionTitle}>Сравнение планов</h2>
                            <div className={styles.titleBar} />
                        </div>

                        <div className={styles.tableWrap}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th className={styles.thFeature}>Функция</th>
                                        {PLANS.map(plan => (
                                            <th key={plan.id} className={`${styles.thPlan} ${plan.highlight ? styles.thPlanHighlight : ''}`}>
                                                <span className={styles.thPlanName}>{plan.name}</span>
                                                <span className={styles.thPlanPrice}>{plan.price}</span>
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {GROUPS.map(group => (
                                        <GroupBody key={group.title} title={group.title} groupId={`group-${group.title}`} rows={group.rows} />
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        <div className={styles.tableNote}>
                            * У Max единственное отличие от Pro — увеличенные лимиты.
                        </div>
                    </div>
                </section>

                <section className={styles.faq} id="faq">
                    <div className={styles.sectionInner}>
                        <div className={styles.sectionHeader}>
                            <h2 className={styles.sectionTitle}>Частые вопросы</h2>
                        </div>
                        <div className={styles.faqList}>
                            {FAQ.map((item, index) => (
                                <div key={item.question} className={`${styles.faqItem} ${openFaq === index ? styles.faqItemOpen : ''}`}>
                                    <button
                                        type="button"
                                        className={styles.faqQuestion}
                                        onClick={() => setOpenFaq(openFaq === index ? null : index)}
                                    >
                                        <span>{item.question}</span>
                                        <span className={styles.faqToggle}>+</span>
                                    </button>
                                    {openFaq === index && (
                                        <div className={styles.faqAnswer}>{item.answer}</div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                <section className={styles.cta}>
                    <div className={styles.ctaInner}>
                        <h2>Поддержите науку о продлении жизни</h2>
                        <p>
                            Проект открыт и бесплатен для всех. Оформите подписку — и вы получите полный набор
                            ИИ-инструментов, а проект — устойчивость и развитие.
                        </p>
                        <div className={styles.ctaButtons}>
                            <button
                                type="button"
                                className={styles.ctaPrimaryBtn}
                                onClick={() => handleCheckout(PLANS[1])}
                                disabled={checkoutPlan !== null}
                            >
                                {checkoutPlan === PLANS[1].id ? 'Перенаправляем…' : 'Оформить подписку'}
                            </button>
                            <a href={FORUM_URL} target="_blank" rel="noopener noreferrer" className={styles.ctaGhostBtn}>
                                Задать вопрос в сообществе
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
}> = ({ plan, current, busy, disabled, onSelect }) => (
    <div className={`${styles.planCard} ${plan.highlight ? styles.planCardHighlight : ''}`}>
        {plan.badge && <div className={styles.planBadge}>{plan.badge}</div>}
        <h3 className={styles.planName}>{plan.name}</h3>
        <div className={styles.planPrice}>{plan.price}</div>
        <div className={styles.planPriceNote}>{plan.priceNote}</div>
        <p className={styles.planDescription}>{plan.description}</p>
        <button
            type="button"
            className={styles.planButton}
            onClick={onSelect}
            disabled={busy || disabled}
        >
            {busy ? 'Перенаправляем…' : current ? 'Текущий тариф' : plan.ctaLabel}
        </button>
    </div>
);

const GroupBody: React.FC<{
    title: string;
    groupId: string;
    rows: readonly { label: string; free: boolean; pro: boolean; max: boolean }[];
}> = ({ title, groupId, rows }) => (
    <>
        <tr className={styles.groupRow}>
            <td className={styles.groupTitle} colSpan={4}>{title}</td>
        </tr>
        {rows.map(row => (
            <tr key={groupId + '-' + row.label}>
                <td className={styles.featureName}>{row.label}</td>
                <td className={styles.featureCell}>{row.free ? <Check /> : <Dash />}</td>
                <td className={styles.featureCell}>{row.pro ? <Check /> : <Dash />}</td>
                <td className={styles.featureCell}>{row.max ? <Check /> : <Dash />}</td>
            </tr>
        ))}
    </>
);

const Check: React.FC = () => (
    <span className={styles.check} aria-hidden="true">✓</span>
);

const Dash: React.FC = () => (
    <span className={styles.dash} aria-hidden="true">—</span>
);

export default SubscriptionUI;
