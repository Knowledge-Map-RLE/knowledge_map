import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import {
    acceptFriend,
    addFriend,
    cancelFriendRequest,
    declineFriend,
    getFriendRequests,
    listUserFriends,
    removeFriend,
} from '../social';

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}

beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('дружба: API-вызовы', () => {
    test('addFriend отправляет POST-заявку', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ success: true, status: 'requested' }));

        const res = await addFriend('b');

        expect(res.status).toBe('requested');
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toContain('/api/social/friends/b');
        expect(init.method).toBe('POST');
    });

    test('acceptFriend подтверждает заявку', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ success: true, is_friend: true }));

        const res = await acceptFriend('b');

        expect(res.is_friend).toBe(true);
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toContain('/api/social/friends/b/accept');
        expect(init.method).toBe('POST');
    });

    test('declineFriend отклоняет заявку', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ success: true }));

        const res = await declineFriend('b');

        expect(res.success).toBe(true);
        expect(fetchMock.mock.calls[0][0]).toContain('/api/social/friends/b/decline');
        expect(fetchMock.mock.calls[0][1].method).toBe('POST');
    });

    test('cancelFriendRequest отзывает заявку', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ success: true }));

        const res = await cancelFriendRequest('b');

        expect(res.success).toBe(true);
        expect(fetchMock.mock.calls[0][0]).toContain('/api/social/friends/b/cancel');
    });

    test('removeFriend удаляет дружбу', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ success: true, is_friend: false }));

        const res = await removeFriend('b');

        expect(res.is_friend).toBe(false);
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toContain('/api/social/friends/b');
        expect(init.method).toBe('DELETE');
    });

    test('ошибка сервера выбрасывает Error', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ detail: 'request_not_found' }, 400));

        await expect(acceptFriend('b')).rejects.toThrow('request_not_found');
    });
});

describe('заявки и публичные друзья', () => {
    test('getFriendRequests возвращает входящие и исходящие', async () => {
        fetchMock.mockResolvedValue(
            jsonResponse({
                success: true,
                incoming: [{ uid: 'x', login: 'x', nickname: 'X' }],
                outgoing: [{ uid: 'y', login: 'y', nickname: 'Y' }],
            }),
        );

        const res = await getFriendRequests();

        expect(res.incoming).toHaveLength(1);
        expect(res.outgoing[0].login).toBe('y');
        expect(fetchMock.mock.calls[0][0]).toContain('/api/social/friends/requests');
    });

    test('listUserFriends возвращает друзей с дистанцией', async () => {
        fetchMock.mockResolvedValue(
            jsonResponse({
                success: true,
                friends: [
                    { uid: 'b', login: 'b', nickname: 'Bravo', distance: 1 },
                    { uid: 'z', login: 'z', nickname: 'Zulu', distance: null },
                ],
            }),
        );

        const res = await listUserFriends('t');

        expect(res.friends[0].distance).toBe(1);
        expect(res.friends[1].distance).toBeNull();
        expect(fetchMock.mock.calls[0][0]).toContain('/api/social/users/t/friends');
    });

    test('listUserFriends кодирует uid в URL', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ success: true, friends: [] }));

        await listUserFriends('user/with space');

        expect(fetchMock.mock.calls[0][0]).toContain('/api/social/users/user%2Fwith%20space/friends');
    });
});