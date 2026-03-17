import React, { useState, useEffect } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { isAuthenticated, isRestoringSession } = useAuth();
  const [hasTimedOut, setHasTimedOut] = useState(false);
  const [showRetry, setShowRetry] = useState(false);
  const navigate = useNavigate();

  // Timeout protection: if session restoration takes more than 25 seconds, show error
  useEffect(() => {
    if (!isRestoringSession) {
      setHasTimedOut(false);
      setShowRetry(false);
      return;
    }

    const timeoutId = setTimeout(() => {
      setHasTimedOut(true);
      setShowRetry(true);
    }, 25000); // 25 seconds timeout

    return () => {
      clearTimeout(timeoutId);
    };
  }, [isRestoringSession]);

  const handleRetry = () => {
    setHasTimedOut(false);
    setShowRetry(false);
    // Force a page reload to retry session restoration
    window.location.reload();
  };

  const handleGoToLogin = () => {
    navigate('/login', { replace: true });
  };

  // Show loading if we're restoring session
  if (isRestoringSession) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-center max-w-md mx-auto px-4">
          {!hasTimedOut ? (
            <>
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600 dark:text-gray-400">
                Restoring session...
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-500 mt-2">
                Please wait while we verify your session
              </p>
            </>
          ) : (
            <>
              <div className="mb-4">
                <svg
                  className="mx-auto h-12 w-12 text-yellow-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                Session Restoration Timeout
              </h2>
              <p className="text-gray-600 dark:text-gray-400 mb-6">
                We're having trouble restoring your session. This might be due to a network issue or an expired session.
              </p>
              {showRetry && (
                <div className="flex gap-3 justify-center">
                  <button
                    onClick={handleRetry}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    Retry
                  </button>
                  <button
                    onClick={handleGoToLogin}
                    className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                  >
                    Go to Login
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
