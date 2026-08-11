import { httpClient as api } from './api/httpClient'
import { clearToken, getToken, saveToken } from './token'
import type {
    User,
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    RecoveryRequest,
    PasswordResetRequest,
    TwoFactorSetupRequest,
    TwoFactorVerifyRequest,
    CaptchaResponse,
} from '../entities/user';

export type {
    User,
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    RecoveryRequest,
    PasswordResetRequest,
    TwoFactorSetupRequest,
    TwoFactorVerifyRequest,
    CaptchaResponse,
} from '../entities/user';

class AuthService {
    setToken(token: string, remember: boolean = true) {
        saveToken(token, remember)
    }

    getToken(): string | null {
        return getToken()
    }

    clearToken() {
        clearToken()
    }

    async register(data: RegisterRequest): Promise<AuthResponse> {
        const response = await api.post('/api/auth/register', data)
        return await response.json()
    }

    async login(data: LoginRequest, rememberMe: boolean = true): Promise<AuthResponse> {
        const response = await api.post('/api/auth/login', { ...data, remember_me: rememberMe })
        const result = await response.json()
        
        if (result.success && result.token) {
            this.setToken(result.token, rememberMe)
        }
        
        return result
    }

    async logout(logoutAll: boolean = false): Promise<{ success: boolean; message: string }> {
        const token = this.getToken()
        if (!token) {
            return { success: false, message: 'Нет активной сессии' }
        }

        try {
            const response = await api.post('/api/auth/logout', { token, logout_all: logoutAll })
            this.clearToken()
            return await response.json()
        } catch {
            this.clearToken()
            return { success: false, message: 'Ошибка при выходе' }
        }
    }

    async verifyToken(): Promise<User | null> {
        const token = this.getToken()
        if (!token) {
            return null
        }

        try {
            const response = await api.post('/api/auth/verify', { token })
            const result = await response.json()
            return result.valid ? result.user : null
        } catch {
            this.clearToken()
            return null
        }
    }

    async recoveryRequest(data: RecoveryRequest): Promise<AuthResponse> {
        const response = await api.post('/api/auth/recovery', data)
        return await response.json()
    }

    async resetPassword(data: PasswordResetRequest): Promise<{ success: boolean; message: string }> {
        const response = await api.post('/api/auth/reset-password', data)
        return await response.json()
    }

    async setup2FA(data: TwoFactorSetupRequest): Promise<AuthResponse> {
        const response = await api.post('/api/auth/2fa/setup', data)
        return await response.json()
    }

    async verify2FA(data: TwoFactorVerifyRequest): Promise<{ success: boolean; message: string }> {
        const response = await api.post('/api/auth/2fa/verify', data)
        return await response.json()
    }

    async getCaptcha(): Promise<CaptchaResponse> {
        const response = await api.get('/api/auth/captcha')
        return await response.json()
    }

    isAuthenticated(): boolean {
        return !!this.getToken()
    }
}

export const authService = new AuthService() 