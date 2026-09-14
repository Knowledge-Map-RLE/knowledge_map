/**
 * Серверный трекинг посещаемости (точная аналитика в БД).
 *
 * Каждый просмотр страницы отправляется fire-and-forget на
 * POST /api/analytics/page-view. Уникальность посетителей и сессий
 * считается на сервере по заголовку X-Client-Session-ID (httpClient
 * добавляет его автоматически). Сервер сам определяет, авторизован ли
 * пользователь, по Bearer-токену — флаг authenticated в теле не отправляется.
 *
 * Ошибки сети/сервера молчат: аналитика не должна ломать UI.
 */

import { httpClient } from './httpClient';

/** Отправляет просмотр страницы на сервер. Не бросает исключений. */
export async function reportPageVisit(route: string): Promise<void> {
  try {
    await httpClient.post('/api/analytics/page-view', {
      route,
      referrer: referrerDomain(),
    });
  } catch (error) {
    console.warn('[analytics] page view report failed:', error);
  }
}

function referrerDomain(): string {
  try {
    const url = new URL(document.referrer);
    return url.hostname || 'direct';
  } catch {
    return 'direct';
  }
}