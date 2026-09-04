export interface BrowserInfo {
    user_agent: string;
    language: string;
    platform: string;
    screen_width: number;
    screen_height: number;
    window_width: number;
    window_height: number;
    timezone: string;
    cookie_enabled: boolean;
    device_memory: number;
    hardware_concurrency: number;
    connection_type: string;
}

export function collectBrowserInfo(): BrowserInfo {
    const nav = navigator as Navigator & {
        deviceMemory?: number;
        connection?: { effectiveType?: string };
    };

    return {
        user_agent: navigator.userAgent,
        language: navigator.language,
        platform: navigator.platform,
        screen_width: screen.width,
        screen_height: screen.height,
        window_width: window.innerWidth,
        window_height: window.innerHeight,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        cookie_enabled: navigator.cookieEnabled,
        device_memory: nav.deviceMemory ?? 0,
        hardware_concurrency: navigator.hardwareConcurrency,
        connection_type: nav.connection?.effectiveType ?? '',
    };
}

export function getAppVersion(): string {
    try {
        return import.meta.env.VITE_APP_VERSION || 'dev';
    } catch {
        return 'dev';
    }
}
