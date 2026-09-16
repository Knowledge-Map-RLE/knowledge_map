import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../../entities/auth/AuthContext';
import { fetchUserMe } from '../../../services/api/user';

interface AdminGuardProps {
  children: ReactNode;
}

export default function AdminGuard({ children }: AdminGuardProps) {
  const { user, isAuthLoading } = useAuth();
  const [role, setRole] = useState<string | null>(null);
  const [roleLoading, setRoleLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (isAuthLoading) return;
      try {
        const me = await fetchUserMe();
        if (!cancelled) setRole(me.role);
      } catch {
        if (!cancelled) setRole(null);
      } finally {
        if (!cancelled) setRoleLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user, isAuthLoading]);

  const loading = isAuthLoading || roleLoading;

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        background: '#0f1117',
        color: '#e0e0e0',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            width: 40,
            height: 40,
            border: '3px solid #2a2d37',
            borderTopColor: '#3b82f6',
            borderRadius: '50%',
            animation: 'spin 0.8s linear infinite',
            margin: '0 auto 12px',
          }} />
          <div style={{ color: '#888', fontSize: '0.875rem' }}>Проверка доступа...</div>
        </div>
      </div>
    );
  }

  if (!user || !user.is_active || role !== 'admin') {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}