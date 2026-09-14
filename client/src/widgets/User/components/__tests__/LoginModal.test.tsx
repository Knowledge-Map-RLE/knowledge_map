import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { LoginModal } from '../LoginModal';

const loginMock = vi.fn();

vi.mock('../../../../services/auth', () => ({
    authService: {
        login: (...args: unknown[]) => loginMock(...args),
    },
}));

function renderModal() {
    const onClose = vi.fn();
    const onSwitchToRecovery = vi.fn();
    const onSuccess = vi.fn();
    const utils = render(
        <LoginModal onClose={onClose} onSwitchToRecovery={onSwitchToRecovery} onSuccess={onSuccess} />,
    );
    return { onClose, onSwitchToRecovery, onSuccess, ...utils };
}

async function fillAndSubmit(utils: ReturnType<typeof renderModal>, remember: boolean) {
    fireEvent.change(screen.getByLabelText('Логин *'), { target: { value: 'user' } });
    fireEvent.change(screen.getByLabelText('Пароль *'), { target: { value: 'secret' } });
    fireEvent.change(screen.getByLabelText('Капча *'), { target: { value: '1234' } });

    const checkbox = screen.getByLabelText('Запомнить меня') as HTMLInputElement;
    if (checkbox.checked !== remember) {
        fireEvent.click(checkbox);
    }

    fireEvent.click(screen.getByRole('button', { name: 'Войти' }));
    await waitFor(() => expect(loginMock).toHaveBeenCalled());
    return loginMock.mock.calls[0];
}

describe('LoginModal', () => {
    beforeEach(() => {
        loginMock.mockReset();
        loginMock.mockResolvedValue({ success: true, user: { uid: 'u1' } });
    });

    afterEach(() => {
        cleanup();
    });

    test('чекбокс «Запомнить меня» отображается и включён по умолчанию', () => {
        renderModal();
        const checkbox = screen.getByLabelText('Запомнить меня') as HTMLInputElement;
        expect(checkbox).toBeInTheDocument();
        expect(checkbox.checked).toBe(true);
    });

    test('с включённой галочкой remember передаётся как true в authService.login', async () => {
        const utils = renderModal();
        const [data, remember] = await fillAndSubmit(utils, true);
        expect(data).toEqual({ login: 'user', password: 'secret', captcha: '1234' });
        expect(remember).toBe(true);
    });

    test('со снятой галочкой remember передаётся как false', async () => {
        const utils = renderModal();
        const [, remember] = await fillAndSubmit(utils, false);
        expect(remember).toBe(false);
    });

    test('при успешном входе вызывается onSuccess с пользователем', async () => {
        const utils = renderModal();
        await fillAndSubmit(utils, true);
        await waitFor(() => expect(utils.onSuccess).toHaveBeenCalledWith({ uid: 'u1' }));
    });

    test('при ошибке входа показывается сообщение', async () => {
        loginMock.mockResolvedValue({ success: false, message: 'Неверный логин или пароль' });
        const utils = renderModal();
        await fillAndSubmit(utils, true);
        await waitFor(() => expect(screen.getByText('Неверный логин или пароль')).toBeInTheDocument());
    });
});