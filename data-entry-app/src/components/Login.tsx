import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Loader2, AlertCircle, Home, Info } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { supabase } from '../lib/supabase';
import { logAction } from '../services/auditLogService';
import logo from '../assets/logo.webp';

interface LoginProps {
  onLogin?: (email: string, password: string) => Promise<void>;
}

const Login: React.FC<LoginProps> = ({ onLogin }) => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loginData, setLoginData] = useState({
    email: '',
    password: '',
  });
  const [showForgotPopup, setShowForgotPopup] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      // Use Supabase Auth for login
      const { data, error: authError } = await supabase.auth.signInWithPassword({
        email: loginData.email.toLowerCase(),
        password: loginData.password,
      });

      if (authError || !data.user) {
        setError(authError?.message || 'Invalid email or password');
        setLoading(false);
        return;
      }

      // Fetch user profile from app_users table
      const { data: userProfile, error: profileError } = await supabase
        .from('app_users')
        .select('*')
        .eq('id', data.user.id)
        .eq('status', 'active')
        .single();

      if (profileError || !userProfile) {
        await supabase.auth.signOut();
        setError('User account not found or inactive');
        setLoading(false);
        return;
      }

      // Create AuthUser object
      const authUser = {
        id: userProfile.id,
        email: userProfile.email,
        name: userProfile.name || userProfile.email,
        first_name: userProfile.first_name || '',
        last_name: userProfile.last_name || '',
        role: userProfile.role,
        permissions: [],
        roles: [],
        created_at: userProfile.created_at,
      };

      if (onLogin) {
        await onLogin(loginData.email, loginData.password);
      } else {
        // Pass the session from signInWithPassword to login function
        await login(authUser, data.session);
      }

      // Log login action
      await logAction(authUser.id, 'LOGIN', 'system', null, {
        email: authUser.email,
        role: authUser.role,
      });

      // Navigate - ProtectedRoute will handle waiting for session restoration if needed
      navigate('/master-entry');
    } catch (err: any) {
      console.error('Login error:', err);
      setError(err.message || 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page min-h-screen flex flex-col relative">

      {/* Top Header Bar */}
      <header className="main-header relative z-10 w-full">
        <div className="container header-bar">
          <div className="brand">
            <img src={logo} alt="Makkal Nalapani" />
            <div className="brand-text">
              <span className="brand-title">Makkal Nalapani</span>
              <span className="brand-subtitle">Melmaruvathur</span>
            </div>
          </div>

          <div className="header-right">
            <nav className="nav-pills">
            <a
              href="https://omsakthi.co.in"
              className="nav-pill-item"
            >
              <Home className="w-4 h-4" />
              Home
            </a>
            <a
              href="https://omsakthi.co.in/about"
              className="nav-pill-item"
            >
              <Info className="w-4 h-4" />
              About
            </a>
            </nav>
          </div>
        </div>
      </header>

      <div className="login-content flex-1">
        <div className="login-center">
          <div className="w-full max-w-md">
            <div className="text-center mb-4">
              <h2 className="text-2xl font-bold" style={{ color: '#222222' }}>
                Admin Portal
              </h2>
            </div>
            <div
              className="rounded-2xl shadow-2xl p-8 border"
              style={{
                backgroundColor: '#ffffff',
                borderColor: '#e2e2e2',
                boxShadow: '0 20px 45px rgba(0, 0, 0, 0.18)',
              }}
            >
              {error && (
                <div className="mb-6 p-4 rounded-lg flex items-center space-x-2" style={{ backgroundColor: '#fff3c4', border: '1px solid #f4b400' }}>
                  <AlertCircle className="w-5 h-5 flex-shrink-0" style={{ color: '#99271A' }} />
                  <span className="text-sm" style={{ color: '#99271A' }}>{error}</span>
                </div>
              )}

          <form onSubmit={handleLogin} className="space-y-6">
            <div>
              <label className="block text-sm font-medium mb-2" style={{ color: '#444444' }}>
                Email
              </label>
              <input
                type="email"
                required
                value={loginData.email}
                onChange={(e) => setLoginData({ ...loginData, email: e.target.value })}
                className="w-full px-4 py-3 rounded-lg transition-colors bg-white text-gray-900"
                style={{
                  border: '1px solid #d7d7d7',
                  boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.06)',
                }}
                placeholder="Enter your email"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2" style={{ color: '#444444' }}>
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={loginData.password}
                  onChange={(e) => setLoginData({ ...loginData, password: e.target.value })}
                  className="w-full px-4 py-3 pr-11 rounded-lg transition-colors bg-white text-gray-900"
                  style={{
                    border: '1px solid #d7d7d7',
                    boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.06)',
                  }}
                  placeholder="Enter your password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 transform -translate-y-1/2"
                  style={{ color: '#666666' }}
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 px-4 rounded-full transition-colors font-semibold disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
              style={{
                backgroundColor: '#99271A',
                color: '#ffffff',
              }}
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Logging in...</span>
                </>
              ) : (
                <span>Login</span>
              )}
            </button>

              </form>
              <div className="mt-6 text-center text-sm">
                <button
                  type="button"
                  onClick={() => setShowForgotPopup(true)}
                  className="underline"
                  style={{ color: '#99271A' }}
                >
                  Forgot password?
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {showForgotPopup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
          <div
            className="absolute inset-0"
            style={{ background: 'rgba(0, 0, 0, 0.4)' }}
            onClick={() => setShowForgotPopup(false)}
          ></div>
          <div
            className="relative z-10 w-full max-w-sm rounded-xl border p-6 text-center"
            style={{ backgroundColor: '#ffffff', borderColor: '#e2e2e2' }}
          >
            <h3 className="text-lg font-semibold mb-2" style={{ color: '#222222' }}>
              Forgot Password
            </h3>
            <p className="text-sm mb-4" style={{ color: '#444444' }}>
              Please contact the developer to reset your password.
            </p>
            <button
              type="button"
              onClick={() => setShowForgotPopup(false)}
              className="px-4 py-2 rounded-full font-semibold"
              style={{ backgroundColor: '#f4b400', color: '#222222' }}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default Login;
