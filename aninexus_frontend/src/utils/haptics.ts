/**
 * Utility for Telegram WebApp Haptic Feedback
 */

export const haptics = {
  light: () => {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light');
  },

  medium: () => {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('medium');
  },

  heavy: () => {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('heavy');
  },

  rigid: () => {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('rigid');
  },

  soft: () => {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('soft');
  },

  notification: (type: 'error' | 'success' | 'warning') => {
    window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred(type);
  },

  selection: () => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
  },
};
