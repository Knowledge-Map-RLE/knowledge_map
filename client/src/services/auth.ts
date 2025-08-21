import { api } from './api'

export interface User {
    uid: string
    login: string
    nickname: string
    is_active: boolean
    is_2fa_enabled: boolean
}

export interface AuthResponse {
    success: boolean
    message: string
    token?: string
    user?: User
    requires_2fa?: boolean
    recovery_keys?: string[]
}

export interface LoginRequest {
    login: string
    password: string
    captcha: string
    device_info?: string
    ip_address?: string
}

export interface RegisterRequest {
    login: string
    password: string
    nickname: string
    captcha: string
}

export interface RecoveryRequest {
    recovery_key: string
    captcha: string
}

export interface PasswordResetRequest {
    user_id: string
    new_password: string
    new_password_confirm: string
}

export interface TwoFactorSetupRequest {
    user_id: string
}

export interface TwoFactorVerifyRequest {
    user_id: string
    code: string
}

export interface CaptchaResponse {
    captcha_id: string
    captcha_image: string
}

class AuthService {
    private token: string | null = null

    setToken(token: string) {
        this.token = token
        localStorage.setItem('auth_token', token)
    }

    getToken(): string | null {
        if (!this.token) {
            this.token = localStorage.getItem('auth_token')
        }
        return this.token
    }

    clearToken() {
        this.token = null
        localStorage.removeItem('auth_token')
    }

    async register(data: RegisterRequest): Promise<AuthResponse> {
        const response = await api.post('/auth/register', data)
        return await response.json()
    }

    async login(data: LoginRequest): Promise<AuthResponse> {
        const response = await api.post('/auth/login', data)
        const result = await response.json()
        
        if (result.success && result.token) {
            this.setToken(result.token)
        }
        
        return result
    }

    async logout(logoutAll: boolean = false): Promise<{ success: boolean; message: string }> {
        const token = this.getToken()
        if (!token) {
            return { success: false, message: 'Нет активной сессии' }
        }

        try {
            const response = await api.post('/auth/logout', { token, logout_all: logoutAll })
            this.clearToken()
            return await response.json()
        } catch (error) {
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
            const response = await api.post('/auth/verify', { token })
            const result = await response.json()
            return result.valid ? result.user : null
        } catch (error) {
            this.clearToken()
            return null
        }
    }

    async recoveryRequest(data: RecoveryRequest): Promise<AuthResponse> {
        const response = await api.post('/auth/recovery', data)
        return await response.json()
    }

    async resetPassword(data: PasswordResetRequest): Promise<{ success: boolean; message: string }> {
        const response = await api.post('/auth/reset-password', data)
        return await response.json()
    }

    async setup2FA(data: TwoFactorSetupRequest): Promise<AuthResponse> {
        const response = await api.post('/auth/2fa/setup', data)
        return await response.json()
    }

    async verify2FA(data: TwoFactorVerifyRequest): Promise<{ success: boolean; message: string }> {
        const response = await api.post('/auth/2fa/verify', data)
        return await response.json()
    }

    async getCaptcha(): Promise<CaptchaResponse> {
        const response = await api.get('/auth/captcha')
        return await response.json()
    }

    isAuthenticated(): boolean {
        return !!this.getToken()
    }
}

export const authService = new AuthService() 