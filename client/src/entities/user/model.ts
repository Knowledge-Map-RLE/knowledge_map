export interface User {
    uid: string;
    login: string;
    nickname: string;
    is_active: boolean;
    is_2fa_enabled: boolean;
}

export interface AuthResponse {
    success: boolean;
    message: string;
    token?: string;
    user?: User;
    requires_2fa?: boolean;
    recovery_keys?: string[];
}

export interface LoginRequest {
    login: string;
    password: string;
    captcha: string;
    device_info?: string;
    ip_address?: string;
}

export interface RegisterRequest {
    login: string;
    password: string;
    nickname: string;
    captcha: string;
}

export interface RecoveryRequest {
    recovery_key: string;
    captcha: string;
}

export interface PasswordResetRequest {
    user_id: string;
    new_password: string;
    new_password_confirm: string;
}

export interface TwoFactorSetupRequest {
    user_id: string;
}

export interface TwoFactorVerifyRequest {
    user_id: string;
    code: string;
}

export interface CaptchaResponse {
    captcha_id: string;
    captcha_image: string;
}
