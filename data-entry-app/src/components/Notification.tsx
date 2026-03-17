import React, { useEffect } from 'react';
import { X, CheckCircle2, AlertCircle, Info, AlertTriangle } from 'lucide-react';

export type NotificationType = 'success' | 'error' | 'info' | 'warning';

export interface Notification {
  id: string;
  message: string;
  type: NotificationType;
  duration?: number;
}

interface NotificationProps {
  notification: Notification;
  onClose: (id: string) => void;
}

const NotificationItem: React.FC<NotificationProps> = ({ notification, onClose }) => {
  useEffect(() => {
    if (notification.duration !== 0) {
      const timer = setTimeout(() => {
        onClose(notification.id);
      }, notification.duration || 5000);

      return () => clearTimeout(timer);
    }
  }, [notification.id, notification.duration, onClose]);

  const getIcon = () => {
    switch (notification.type) {
      case 'success':
        return <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />;
      case 'error':
        return <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400" />;
      case 'warning':
        return <AlertTriangle className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />;
      case 'info':
        return <Info className="w-5 h-5 text-blue-600 dark:text-blue-400" />;
      default:
        return <Info className="w-5 h-5 text-gray-600 dark:text-gray-400" />;
    }
  };

  const getBgColor = () => {
    switch (notification.type) {
      case 'success':
        return 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800';
      case 'error':
        return 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800';
      case 'warning':
        return 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800';
      case 'info':
        return 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800';
      default:
        return 'bg-gray-50 dark:bg-gray-900/20 border-gray-200 dark:border-gray-800';
    }
  };

  const getTextColor = () => {
    switch (notification.type) {
      case 'success':
        return 'text-green-700 dark:text-green-300';
      case 'error':
        return 'text-red-700 dark:text-red-300';
      case 'warning':
        return 'text-yellow-700 dark:text-yellow-300';
      case 'info':
        return 'text-blue-700 dark:text-blue-300';
      default:
        return 'text-gray-700 dark:text-gray-300';
    }
  };

  return (
    <div
      className={`${getBgColor()} ${getTextColor()} border rounded-lg shadow-lg p-4 mb-3 min-w-[300px] max-w-[400px] flex items-start gap-3 animate-slide-in`}
    >
      <div className="flex-shrink-0">{getIcon()}</div>
      <div className="flex-1 text-sm">{notification.message}</div>
      <button
        onClick={() => onClose(notification.id)}
        className="flex-shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};

interface NotificationContainerProps {
  notifications: Notification[];
  onClose: (id: string) => void;
}

export const NotificationContainer: React.FC<NotificationContainerProps> = ({
  notifications,
  onClose,
}) => {
  if (notifications.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[9999] flex flex-col items-end">
      {notifications.map((notification) => (
        <NotificationItem
          key={notification.id}
          notification={notification}
          onClose={onClose}
        />
      ))}
    </div>
  );
};

// Hook for managing notifications
let notificationIdCounter = 0;

export const useNotification = () => {
  const [notifications, setNotifications] = React.useState<Notification[]>([]);

  const showNotification = (
    message: string,
    type: NotificationType = 'info',
    duration: number = 5000
  ) => {
    const id = `notification-${++notificationIdCounter}`;
    const notification: Notification = {
      id,
      message,
      type,
      duration,
    };

    setNotifications((prev) => [...prev, notification]);
  };

  const removeNotification = (id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  };

  return {
    notifications,
    showNotification,
    removeNotification,
    showSuccess: (message: string, duration?: number) =>
      showNotification(message, 'success', duration),
    showError: (message: string, duration?: number) =>
      showNotification(message, 'error', duration),
    showWarning: (message: string, duration?: number) =>
      showNotification(message, 'warning', duration),
    showInfo: (message: string, duration?: number) =>
      showNotification(message, 'info', duration),
  };
};
