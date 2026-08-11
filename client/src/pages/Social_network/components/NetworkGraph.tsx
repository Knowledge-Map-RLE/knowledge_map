import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as PIXI from 'pixi.js';
import {
    addFriend,
    getGraphUser,
    getSocialGraph,
    joinCommunity,
    leaveCommunity,
    removeFriend,
    socialImageUrl,
    type SocialGraph,
    type SocialGraphEdge,
    type SocialGraphNode,
} from '../../../services/api/social';
import { useRequireAuth } from '../../../shared/hooks/useRequireAuth';
import { useToast } from '../../../shared/ui/Toast';
import { MdPerson, MdAccountBalance } from 'react-icons/md';
import { GraphContextMenu, type GraphMenuAction } from './GraphContextMenu';
import s from '../Social_network.module.css';

interface Position {
    x: number;
    y: number;
}

interface View {
    scale: number;
    tx: number;
    ty: number;
}

export interface GraphCallbacks {
    onOpenChat: (targetType: 'user' | 'community', uid: string) => void;
    onOpenProfile: (uid: string) => void;
}

interface Props extends Partial<GraphCallbacks> {
    myUid?: string;
    compact?: boolean;
}

const H = 540;
const USER_R = 18;
const AVATAR_R = 14;
const COM_W = 130;
const COM_H = 32;

const FONT = '"Segoe UI", Roboto, Arial, sans-serif';

const USER_FILL = 0x3b82f6;
const USER_STROKE = 0x1e3a8a;
const ME_STROKE = 0xf59e0b;
const COM_FILL = 0x8b5cf6;
const COM_STROKE = 0x5b21b6;
const SELECT_STROKE = 0x0f172a;

function computeLayout(nodes: SocialGraphNode[], edges: SocialGraphEdge[], width: number, height: number): Map<string, Position> {
    const n = nodes.length;
    const pos = new Map<string, Position>();
    if (n === 0) return pos;
    const vel = new Map<string, { vx: number; vy: number }>();
    const centerX = width / 2;
    const centerY = height / 2;

    nodes.forEach((node, i) => {
        const angle = (2 * Math.PI * i) / n;
        pos.set(node.id, { x: centerX + Math.cos(angle) * 180, y: centerY + Math.sin(angle) * 140 });
        vel.set(node.id, { vx: 0, vy: 0 });
    });

    const repulsion = 11000;
    const springLen = 140;
    const springK = 0.025;
    const damping = 0.85;

    for (let iter = 0; iter < 300; iter++) {
        for (let i = 0; i < n; i++) {
            for (let j = i + 1; j < n; j++) {
                const a = pos.get(nodes[i].id)!;
                const b = pos.get(nodes[j].id)!;
                let dx = a.x - b.x;
                let dy = a.y - b.y;
                let dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 10) dist = 10;
                const force = repulsion / (dist * dist);
                dx /= dist;
                dy /= dist;
                const va = vel.get(nodes[i].id)!;
                const vb = vel.get(nodes[j].id)!;
                va.vx += dx * force;
                va.vy += dy * force;
                vb.vx -= dx * force;
                vb.vy -= dy * force;
            }
        }
        for (const edge of edges) {
            const a = pos.get(edge.source);
            const b = pos.get(edge.target);
            if (!a || !b) continue;
            let dx = a.x - b.x;
            let dy = a.y - b.y;
            let dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 1) dist = 1;
            const f = (dist - springLen) * springK;
            dx /= dist;
            dy /= dist;
            const va = vel.get(edge.source)!;
            const vb = vel.get(edge.target)!;
            va.vx -= dx * f;
            va.vy -= dy * f;
            vb.vx += dx * f;
            vb.vy += dy * f;
        }
        for (const node of nodes) {
            const p = pos.get(node.id)!;
            const v = vel.get(node.id)!;
            v.vx *= damping;
            v.vy *= damping;
            p.x += v.vx;
            p.y += v.vy;
            const pad = 50;
            if (p.x < pad) { p.x = pad; v.vx *= -0.5; }
            if (p.x > width - pad) { p.x = width - pad; v.vx *= -0.5; }
            if (p.y < pad) { p.y = pad; v.vy *= -0.5; }
            if (p.y > height - pad) { p.y = height - pad; v.vy *= -0.5; }
        }
    }
    return pos;
}

function mergeGraph(base: SocialGraph, extra: SocialGraph): SocialGraph {
    const nodes = new Map<string, SocialGraphNode>();
    for (const node of [...base.nodes, ...extra.nodes]) nodes.set(node.id, node);
    const edges = new Map<string, SocialGraphEdge>();
    for (const edge of [...base.edges, ...extra.edges]) {
        edges.set(`${edge.source}|${edge.target}|${edge.type}`, edge);
    }
    return { success: true, nodes: [...nodes.values()], edges: [...edges.values()] };
}

export function NetworkGraph({ myUid = '', onOpenChat, onOpenProfile, compact = false }: Props) {
    const { error: toastError, success: toastSuccess } = useToast();
    const requireAuth = useRequireAuth();
    const canvasWrapRef = useRef<HTMLDivElement | null>(null);
    const appRef = useRef<PIXI.Application | null>(null);
    const viewContainerRef = useRef<PIXI.Container | null>(null);
    const edgeGRef = useRef<PIXI.Graphics | null>(null);
    const nodeGRef = useRef<PIXI.Graphics | null>(null);
    const avatarLayerRef = useRef<PIXI.Container | null>(null);
    const textLayerRef = useRef<PIXI.Container | null>(null);

    const viewRef = useRef<View>({ scale: 1, tx: 0, ty: 0 });
    const posRef = useRef<Map<string, Position>>(new Map());
    const nodeByIdRef = useRef<Map<string, SocialGraphNode>>(new Map());
    const visibleIdsRef = useRef<Set<string>>(new Set());
    const visibleNodesRef = useRef<SocialGraphNode[]>([]);
    const visibleEdgesRef = useRef<SocialGraphEdge[]>([]);
    const selectedRef = useRef<SocialGraphNode | null>(null);
    const myUidRef = useRef(myUid);
    myUidRef.current = myUid;
    const spritesRef = useRef<Map<string, { sprite: PIXI.Sprite; mask: PIXI.Graphics; text: PIXI.Text; avatarKey: string }>>(new Map());
    const textureCacheRef = useRef<Map<string, Promise<PIXI.Texture>>>(new Map());

    const dragRef = useRef<{ nodeId: string; lastX: number; lastY: number } | null>(null);
    const panRef = useRef<{ lastX: number; lastY: number } | null>(null);
    const lastTapRef = useRef<{ id: string; t: number } | null>(null);
    const rafRef = useRef<number | null>(null);

    const [graph, setGraph] = useState<SocialGraph | null>(null);
    const [loading, setLoading] = useState(true);
    const [appReady, setAppReady] = useState(false);
    const [query, setQuery] = useState('');
    const [filter, setFilter] = useState<'all' | 'user' | 'community'>('all');
    const [selected, setSelected] = useState<SocialGraphNode | null>(null);
    const [menu, setMenu] = useState<{ node: SocialGraphNode; x: number; y: number } | null>(null);

    const callbacksRef = useRef<GraphCallbacks>({
        onOpenChat: (targetType, uid) => {
            if (onOpenChat) onOpenChat(targetType, uid);
        },
        onOpenProfile: (uid) => {
            if (onOpenProfile) onOpenProfile(uid);
        },
    });
    callbacksRef.current.onOpenChat = onOpenChat ?? (() => undefined);
    callbacksRef.current.onOpenProfile = onOpenProfile ?? (() => undefined);

    // ── Загрузка графа ───────────────────────────────────────────────────────

    const loadGraph = useCallback(async () => {
        try {
            const res = await getSocialGraph();
            setGraph(res);
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки графа');
        } finally {
            setLoading(false);
        }
    }, [toastError]);

    useEffect(() => {
        loadGraph();
    }, [loadGraph]);

    useEffect(() => {
        const onRefresh = () => void loadGraph();
        window.addEventListener('social:graph-refresh', onRefresh);
        return () => window.removeEventListener('social:graph-refresh', onRefresh);
    }, [loadGraph]);

    useEffect(() => {
        selectedRef.current = selected;
    }, [selected]);

    // ── Инициализация Pixi ───────────────────────────────────────────────────

    useEffect(() => {
        const wrap = canvasWrapRef.current;
        if (!wrap) return;
        const width = wrap.clientWidth || 800;

        const app = new PIXI.Application();
        let disposed = false;

        void app.init({
            width,
            height: H,
            antialias: true,
            backgroundColor: 0xffffff,
            resolution: 1,
        }).then(() => {
            if (disposed) {
                app.destroy(true, { children: true });
                return;
            }
            appRef.current = app;
            wrap.appendChild(app.canvas);
            app.canvas.style.width = '100%';
            app.canvas.style.display = 'block';
            app.canvas.style.borderRadius = '12px';

            const edgeG = new PIXI.Graphics();
            const nodeG = new PIXI.Graphics();
            const avatarLayer = new PIXI.Container();
            const textLayer = new PIXI.Container();
            const viewContainer = new PIXI.Container();
            viewContainer.addChild(edgeG, nodeG, avatarLayer, textLayer);
            app.stage.addChild(viewContainer);

            viewContainerRef.current = viewContainer;
            edgeGRef.current = edgeG;
            nodeGRef.current = nodeG;
            avatarLayerRef.current = avatarLayer;
            textLayerRef.current = textLayer;

            app.stage.eventMode = 'static';
            app.stage.hitArea = new PIXI.Rectangle(0, 0, width, H);
            app.stage.cursor = 'default';

            app.stage.on('pointerdown', (e: PIXI.FederatedPointerEvent) => onPointerDown(e));
            app.stage.on('pointermove', (e: PIXI.FederatedPointerEvent) => onPointerMove(e));
            app.stage.on('pointerup', onPointerUp);
            app.stage.on('pointerupoutside', onPointerUp);
            app.stage.on('rightdown', (e: PIXI.FederatedPointerEvent) => onRightDown(e));

            app.canvas.addEventListener('wheel', onWheel, { passive: false });
            app.canvas.addEventListener('contextmenu', (ev) => ev.preventDefault());
            setAppReady(true);
        });

        return () => {
            disposed = true;
            if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
            if (appRef.current === app) {
                app.destroy(true, { children: true });
                appRef.current = null;
            }
            viewContainerRef.current = null;
            spritesRef.current.clear();
            textureCacheRef.current.clear();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ── Видимость / layout ───────────────────────────────────────────────────

    const { visibleNodes, visibleEdges } = useMemo(() => {
        if (!graph) return { visibleNodes: [] as SocialGraphNode[], visibleEdges: [] as SocialGraphEdge[] };
        const q = query.trim().toLowerCase();
        const nodes = graph.nodes.filter((node) => {
            if (filter !== 'all' && node.type !== filter) return false;
            if (!q) return true;
            const hay = `${node.label} ${node.login ?? ''} ${node.description ?? ''}`.toLowerCase();
            return hay.includes(q);
        });
        const ids = new Set(nodes.map((n) => n.id));
        const edges = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
        return { visibleNodes: nodes, visibleEdges: edges };
    }, [graph, query, filter]);

    // ── Отображение ──────────────────────────────────────────────────────────

    const ensureSprite = useCallback((id: string, node: SocialGraphNode, layer: PIXI.Container, textLayer: PIXI.Container) => {
        let entry = spritesRef.current.get(id);
        const avatarKey = node.avatar_key ?? '';
        if (entry) {
            if (entry.avatarKey !== avatarKey) {
                entry.avatarKey = avatarKey;
                entry.sprite.visible = !!avatarKey;
                if (avatarKey) {
                    let load = textureCacheRef.current.get(avatarKey);
                    if (!load) {
                        load = PIXI.Assets.load(socialImageUrl(avatarKey)).catch(() => null) as Promise<PIXI.Texture | null>;
                        textureCacheRef.current.set(avatarKey, load as Promise<PIXI.Texture>);
                    }
                    void load.then((tex) => {
                        if (tex && entry.avatarKey === avatarKey) {
                            entry.sprite.texture = tex;
                            entry.sprite.visible = true;
                        }
                    });
                }
            }
            return entry;
        }
        const sprite = new PIXI.Sprite(PIXI.Texture.EMPTY);
        const mask = new PIXI.Graphics();
        mask.circle(0, 0, AVATAR_R).fill(0xffffff);
        sprite.anchor.set(0.5);
        sprite.width = AVATAR_R * 2;
        sprite.height = AVATAR_R * 2;
        sprite.visible = !!avatarKey;
        sprite.mask = mask;
        layer.addChild(mask);
        layer.addChild(sprite);

        const text = new PIXI.Text({
            text: node.type === 'user' ? node.label : node.label,
            style: {
                fontFamily: FONT,
                fontSize: 12,
                fontWeight: '600',
                fill: node.type === 'user' ? 0x334155 : 0xffffff,
                stroke: node.type === 'community' ? { color: 0x000000, width: 2, alpha: 0.35 } : undefined,
            },
        });
        text.anchor.set(0.5);
        textLayer.addChild(text);

        entry = { sprite, mask, text, avatarKey };
        spritesRef.current.set(id, entry);

        if (avatarKey) {
            let load = textureCacheRef.current.get(avatarKey);
            if (!load) {
                load = PIXI.Assets.load(socialImageUrl(avatarKey)).catch(() => null) as Promise<PIXI.Texture | null>;
                textureCacheRef.current.set(avatarKey, load as Promise<PIXI.Texture>);
            }
            void load.then((tex) => {
                if (tex && entry.avatarKey === avatarKey) {
                    sprite.texture = tex;
                    sprite.visible = true;
                }
            });
        }
        return entry;
    }, []);

    const drawFrame = useCallback(() => {
        const app = appRef.current;
        const viewContainer = viewContainerRef.current;
        const edgeG = edgeGRef.current;
        const nodeG = nodeGRef.current;
        const avatarLayer = avatarLayerRef.current;
        const textLayer = textLayerRef.current;
        if (!app || !viewContainer || !edgeG || !nodeG || !avatarLayer || !textLayer) return;

        const pos = posRef.current;
        const edges = visibleEdgesRef.current;
        const nodeById = nodeByIdRef.current;
        const selId = selectedRef.current?.id ?? null;

        edgeG.clear();
        for (const edge of edges) {
            const a = pos.get(edge.source);
            const b = pos.get(edge.target);
            if (!a || !b) continue;
            const isFriend = edge.type === 'friend';
            edgeG.moveTo(a.x, a.y).lineTo(b.x, b.y).stroke({
                width: isFriend ? 2 : 1.5,
                color: isFriend ? 0x3b82f6 : 0x94a3b8,
                cap: 'round',
                join: 'round',
            });
        }

        nodeG.clear();
        for (const id of visibleIdsRef.current) {
            const node = nodeById.get(id);
            const p = pos.get(id);
            if (!node || !p) continue;
            const isUser = node.type === 'user';
            const isSelected = selId === id;
            const isMe = node.is_me || node.id === myUidRef.current;

            if (isUser) {
                nodeG.circle(p.x, p.y, USER_R).fill(USER_FILL).stroke({
                    width: isMe ? 3 : isSelected ? 3 : 2,
                    color: isMe ? ME_STROKE : isSelected ? SELECT_STROKE : USER_STROKE,
                });
                if (isSelected) {
                    nodeG.circle(p.x, p.y, USER_R + 5).fill({ color: 0xffffff, alpha: 0 }).stroke({
                        width: 1.5,
                        color: SELECT_STROKE,
                        alpha: 0.4,
                    });
                }
            } else {
                nodeG.roundRect(p.x - COM_W / 2, p.y - COM_H / 2, COM_W, COM_H, 10).fill(COM_FILL).stroke({
                    width: isSelected ? 3 : 2,
                    color: isSelected ? SELECT_STROKE : COM_STROKE,
                });
            }
        }

        for (const id of visibleIdsRef.current) {
            const node = nodeById.get(id);
            const p = pos.get(id);
            const entry = spritesRef.current.get(id);
            if (!node || !p) continue;
            if (entry) {
                const isUser = node.type === 'user';
                const textOffset = isUser ? USER_R + 16 : COM_H / 2 + 14;
                entry.sprite.position.set(p.x, p.y);
                entry.mask.position.set(p.x, p.y);
                entry.text.position.set(p.x, p.y + textOffset);
                entry.text.visible = true;
                const label = node.label.length > 26 ? node.label.slice(0, 25) + '…' : node.label;
                if (entry.text.text !== label) entry.text.text = label;
            }
        }
    }, []);

    const applyView = useCallback(() => {
        const viewContainer = viewContainerRef.current;
        if (!viewContainer) return;
        viewContainer.scale.set(viewRef.current.scale);
        viewContainer.position.set(viewRef.current.tx, viewRef.current.ty);
    }, []);

    // ── Анимация появления ───────────────────────────────────────────────────

    useEffect(() => {
        const app = appRef.current;
        if (!app) return;
        const nodeById = new Map<string, SocialGraphNode>(visibleNodes.map((n) => [n.id, n]));
        nodeByIdRef.current = nodeById;
        visibleIdsRef.current = new Set(visibleNodes.map((n) => n.id));
        visibleNodesRef.current = visibleNodes;
        visibleEdgesRef.current = visibleEdges;

        for (const id of spritesRef.current.keys()) {
            if (!visibleIdsRef.current.has(id)) {
                const entry = spritesRef.current.get(id);
                if (entry) {
                    entry.sprite.destroy();
                    entry.mask.destroy();
                    entry.text.destroy();
                }
                spritesRef.current.delete(id);
            }
        }

        const avatarLayer = avatarLayerRef.current;
        const textLayer = textLayerRef.current;
        if (avatarLayer && textLayer) {
            for (const node of visibleNodes) ensureSprite(node.id, node, avatarLayer, textLayer);
        }

        const target = computeLayout(visibleNodes, visibleEdges, app.screen.width, H);
        posRef.current = target;

        const start = new Map<string, Position>();
        for (const node of visibleNodes) {
            start.set(node.id, {
                x: app.screen.width / 2 + (Math.random() - 0.5) * app.screen.width * 0.5,
                y: H / 2 + (Math.random() - 0.5) * H * 0.5,
            });
        }
        const t0 = performance.now();
        const animate = () => {
            const k = Math.min((performance.now() - t0) / 700, 1);
            const e = 1 - Math.pow(1 - k, 3);
            for (const node of visibleNodes) {
                const s = start.get(node.id);
                const t = target.get(node.id);
                if (!s || !t) continue;
                posRef.current.set(node.id, { x: s.x + (t.x - s.x) * e, y: s.y + (t.y - s.y) * e });
            }
            drawFrame();
            if (k < 1) {
                rafRef.current = requestAnimationFrame(animate);
            } else {
                rafRef.current = null;
            }
        };
        if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
        rafRef.current = requestAnimationFrame(animate);
    }, [visibleNodes, visibleEdges, appReady, drawFrame, ensureSprite]);

    // ── Действия ─────────────────────────────────────────────────────────────

    const reload = useCallback(async () => {
        try {
            const res = await getSocialGraph();
            setGraph(res);
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка обновления графа');
        }
    }, [toastError]);

    const performFriendAction = useCallback(async (node: SocialGraphNode) => {
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы добавлять друзей')) return;
        try {
            if (node.is_friend) {
                await removeFriend(node.id);
                toastSuccess('Пользователь удалён из друзей');
            } else {
                await addFriend(node.id);
                toastSuccess('Запрос дружбы отправлен');
            }
            await reload();
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка изменения дружбы');
        }
    }, [requireAuth, reload, toastSuccess, toastError]);

    const performJoinAction = useCallback(async (node: SocialGraphNode) => {
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы вступать в сообщества')) return;
        try {
            if (node.is_member) {
                await leaveCommunity(node.id);
                toastSuccess('Вы покинули сообщество');
            } else {
                await joinCommunity(node.id);
                toastSuccess('Вы вступили в сообщество');
            }
            await reload();
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка вступления в сообщество');
        }
    }, [requireAuth, reload, toastSuccess, toastError]);

    const handleDoubleClick = useCallback(async (node: SocialGraphNode) => {
        if (node.type === 'user') {
            try {
                const extra = await getGraphUser(node.id);
                if (extra.success) {
                    setGraph((g) => (g ? mergeGraph(g, extra) : extra));
                }
            } catch (e) {
                toastError(e instanceof Error ? e.message : 'Ошибка расширения графа');
            }
        } else {
            callbacksRef.current.onOpenChat('community', node.id);
        }
    }, [toastError]);

    const handleMenuAction = useCallback(async (action: GraphMenuAction) => {
        const node = menu?.node;
        if (!node) return;
        const done = () => setMenu(null);
        switch (action) {
            case 'profile':
                callbacksRef.current.onOpenProfile(node.id);
                done();
                break;
            case 'chat':
                callbacksRef.current.onOpenChat(node.type, node.id);
                done();
                break;
            case 'toggleFriend':
                await performFriendAction(node);
                done();
                break;
            case 'toggleJoin':
                await performJoinAction(node);
                done();
                break;
            case 'center': {
                const app = appRef.current;
                if (app) {
                    const view = viewRef.current;
                    const W = app.screen.width;
                    const k = Math.min(W / 900, 1.4);
                    view.scale = Math.max(k, 0.4);
                    view.tx = W / 2 - (W / 2) * view.scale;
                    view.ty = H / 2 - (H / 2) * view.scale;
                    applyView();
                }
                done();
                break;
            }
        }
    }, [menu, applyView, performFriendAction, performJoinAction]);

    // ── Взаимодействие ───────────────────────────────────────────────────────

    const toWorld = useCallback((gx: number, gy: number): Position => {
        const view = viewRef.current;
        return { x: (gx - view.tx) / view.scale, y: (gy - view.ty) / view.scale };
    }, []);

    const hitTest = useCallback((gx: number, gy: number): SocialGraphNode | null => {
        const w = toWorld(gx, gy);
        const ids = [...visibleIdsRef.current].reverse();
        for (const id of ids) {
            const node = nodeByIdRef.current.get(id);
            const p = posRef.current.get(id);
            if (!node || !p) continue;
            if (node.type === 'user') {
                const d = Math.hypot(w.x - p.x, w.y - p.y);
                if (d <= USER_R + 8) return node;
            } else {
                const dx = Math.abs(w.x - p.x);
                const dy = Math.abs(w.y - p.y);
                if (dx <= COM_W / 2 + 4 && dy <= COM_H / 2 + 4) return node;
            }
        }
        return null;
    }, [toWorld]);

    const onPointerDown = useCallback((e: PIXI.FederatedPointerEvent) => {
        setMenu(null);
        const node = hitTest(e.global.x, e.global.y);
        if (node) {
            setSelected(node);
            const now = performance.now();
            const last = lastTapRef.current;
            if (last && last.id === node.id && now - last.t < 400) {
                lastTapRef.current = null;
                void handleDoubleClick(node);
                return;
            }
            lastTapRef.current = { id: node.id, t: now };
            dragRef.current = { nodeId: node.id, lastX: e.global.x, lastY: e.global.y };
        } else {
            panRef.current = { lastX: e.global.x, lastY: e.global.y };
        }
    }, [hitTest, handleDoubleClick]);

    const onPointerMove = useCallback((e: PIXI.FederatedPointerEvent) => {
        if (dragRef.current) {
            const nodeId = dragRef.current.nodeId;
            const w = toWorld(e.global.x, e.global.y);
            posRef.current.set(nodeId, w);
            dragRef.current.lastX = e.global.x;
            dragRef.current.lastY = e.global.y;
            drawFrame();
        } else if (panRef.current) {
            const view = viewRef.current;
            view.tx += e.global.x - panRef.current.lastX;
            view.ty += e.global.y - panRef.current.lastY;
            panRef.current.lastX = e.global.x;
            panRef.current.lastY = e.global.y;
            applyView();
        }
    }, [toWorld, drawFrame, applyView]);

    const onPointerUp = useCallback(() => {
        dragRef.current = null;
        panRef.current = null;
    }, []);

    const onRightDown = useCallback((e: PIXI.FederatedPointerEvent) => {
        const node = hitTest(e.global.x, e.global.y);
        if (!node) return;
        const wrap = canvasWrapRef.current;
        const rect = wrap?.getBoundingClientRect();
        const x = e.global.x - (rect?.left ?? 0);
        const y = e.global.y - (rect?.top ?? 0);
        setSelected(node);
        setMenu({ node, x, y });
    }, [hitTest]);

    const onWheel = useCallback((ev: WheelEvent) => {
        const app = appRef.current;
        if (!app) return;
        ev.preventDefault();
        const canvas = app.canvas;
        const rect = canvas.getBoundingClientRect();
        const mx = ev.clientX - rect.left;
        const my = ev.clientY - rect.top;
        const view = viewRef.current;
        const factor = ev.deltaY < 0 ? 1.12 : 0.89;
        const ns = Math.min(Math.max(view.scale * factor, 0.2), 3);
        const world = toWorld(mx, my);
        view.scale = ns;
        view.tx = mx - world.x * ns;
        view.ty = my - world.y * ns;
        applyView();
    }, [toWorld, applyView]);

    // ── Resize ───────────────────────────────────────────────────────────────

    useEffect(() => {
        const wrap = canvasWrapRef.current;
        const app = appRef.current;
        if (!wrap || !app) return;
        const ro = new ResizeObserver(() => {
            const w = wrap.clientWidth;
            if (w > 0 && app.screen.width !== w) {
                app.renderer.resize(w, H);
                app.stage.hitArea = new PIXI.Rectangle(0, 0, w, H);
                const view = viewRef.current;
                const worldW = (w - view.tx) / view.scale;
                const viewH = (H - view.ty) / view.scale;
                if (worldW < 300 || viewH < 200) {
                    const k = Math.min(w / 900, 1.4);
                    view.scale = Math.max(k, 0.4);
                    view.tx = w / 2 - (w / 2) * view.scale;
                    view.ty = H / 2 - (H / 2) * view.scale;
                    applyView();
                }
                drawFrame();
            }
        });
        ro.observe(wrap);
        return () => ro.disconnect();
    }, [applyView, drawFrame]);

    const userCount = useMemo(
        () => (graph ? graph.nodes.filter((n) => n.type === 'user').length : 0),
        [graph],
    );
    const communityCount = useMemo(
        () => (graph ? graph.nodes.filter((n) => n.type === 'community').length : 0),
        [graph],
    );

    return (
        <div className={s.panel}>
            <div className={s.panelHead}>
                <div className={s.panelTitle}>
                    Карта сети
                    {!compact && ` — ${userCount} пользователей, ${communityCount} сообществ`}
                </div>
            </div>
            <div className={s.graphToolbar}>
                <input
                    className={s.graphSearch}
                    placeholder="Поиск по имени…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                />
                <div className={s.graphFilter}>
                    {(['all', 'user', 'community'] as const).map((f) => (
                        <button
                            key={f}
                            className={filter === f ? `${s.graphFilterBtn} ${s.graphFilterActive}` : s.graphFilterBtn}
                            onClick={() => setFilter(f)}
                        >
                            {f === 'all' ? 'Все' : f === 'user' ? 'Люди' : 'Сообщ.'}
                        </button>
                    ))}
                </div>
            </div>
            {!compact && (
                <div className={s.legend}>
                    <span className={s.legendItem}><span className={`${s.legendSwatch} ${s.swatchUser}`} />Пользователь</span>
                    <span className={s.legendItem}><span className={`${s.legendSwatch} ${s.swatchCommunity}`} />Сообщество</span>
                    <span className={s.legendItem}><span className={s.legendLineFriend} />Дружба</span>
                    <span className={s.legendItem}><span className={s.legendLineMember} />Членство</span>
                </div>
            )}
            <div className={s.graphWrap} ref={canvasWrapRef}>
                {loading && <div className={s.graphOverlay}><div className={s.hint}>Загрузка графа…</div></div>}
                {!loading && (!graph || graph.nodes.length === 0) && (
                    <div className={s.graphOverlay}>
                        <div className={s.hint}>Граф пуст — добавьте друзей или вступите в сообщества</div>
                    </div>
                )}
                {selected && (
                    <div className={s.graphInfo}>
                        <div className={s.graphInfoName}>
                            {selected.type === 'user' ? <MdPerson /> : <MdAccountBalance />} {selected.label}
                        </div>
                        <div className={s.graphInfoMeta}>
                            {selected.type === 'user'
                                ? `${selected.friend_count ?? 0} друзей · @${selected.login ?? ''}`
                                : `${selected.member_count ?? 0} участников`}
                        </div>
                        <div className={s.graphInfoActions}>
                            <button className={s.ghostBtn} onClick={() => callbacksRef.current.onOpenProfile(selected.id)}>
                                Профиль
                            </button>
                            <button className={s.ghostBtn} onClick={() => callbacksRef.current.onOpenChat(selected.type, selected.id)}>
                                Чат
                            </button>
                            {selected.type === 'user' ? (
                                <button
                                    className={s.ghostBtn}
                                    onClick={() => void performFriendAction(selected)}
                                >
                                    {selected.is_friend ? 'Убрать из друзей' : 'Добавить в друзья'}
                                </button>
                            ) : (
                                <button
                                    className={s.ghostBtn}
                                    onClick={() => void performJoinAction(selected)}
                                >
                                    {selected.is_member ? 'Покинуть' : 'Вступить'}
                                </button>
                            )}
                        </div>
                    </div>
                )}
                {menu && (
                    <GraphContextMenu
                        node={menu.node}
                        x={menu.x}
                        y={menu.y}
                        viewport={{ width: canvasWrapRef.current?.clientWidth ?? 800, height: H }}
                        onAction={(action) => void handleMenuAction(action)}
                        onClose={() => setMenu(null)}
                    />
                )}
            </div>
            <div className={s.graphHints}>
                {compact ? 'ЛКМ — выбрать · ПКМ — меню · зум колесом' : 'ЛКМ — выбрать и перетащить · ПКМ — контекстное меню · колесо — зум · двойной клик по пользователю — раскрыть'}
            </div>
        </div>
    );
}
