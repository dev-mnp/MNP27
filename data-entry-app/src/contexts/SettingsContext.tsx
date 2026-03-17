import React, { createContext, useContext, useEffect, useState } from 'react';

interface SettingsContextType {
  // Theme settings
  theme: 'light' | 'dark';
  actualTheme: 'light' | 'dark';
  setTheme: (theme: 'light' | 'dark') => void;
  
  // Display settings
  density: 'compact' | 'comfortable' | 'spacious';
  setDensity: (density: 'compact' | 'comfortable' | 'spacious') => void;
  animations: boolean;
  setAnimations: (enabled: boolean) => void;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export const useSettings = () => {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
};

interface SettingsProviderProps {
  children: React.ReactNode;
}

const defaultSettings = {
  theme: 'light' as const,
  density: 'comfortable' as const,
  animations: true,
};

export const SettingsProvider: React.FC<SettingsProviderProps> = ({ children }) => {
  // Load settings from localStorage or use defaults
  const loadSetting = <T,>(key: string, defaultValue: T): T => {
    try {
      const saved = localStorage.getItem(`app-${key}`);
      return saved ? JSON.parse(saved) : defaultValue;
    } catch {
      return defaultValue;
    }
  };

  const saveSetting = (key: string, value: any) => {
    localStorage.setItem(`app-${key}`, JSON.stringify(value));
  };

  // Theme settings
  const [theme, setThemeState] = useState<'light' | 'dark'>(() => {
    const savedTheme = loadSetting('theme', defaultSettings.theme);
    // Ensure saved theme is only 'light' or 'dark', default to 'light' if invalid
    return (savedTheme === 'light' || savedTheme === 'dark') ? savedTheme : 'light';
  });
  const [actualTheme, setActualTheme] = useState<'light' | 'dark'>(theme);

  // Display settings
  const [density, setDensityState] = useState<'compact' | 'comfortable' | 'spacious'>(() =>
    loadSetting('density', defaultSettings.density)
  );
  const [animations, setAnimationsState] = useState<boolean>(() =>
    loadSetting('animations', defaultSettings.animations)
  );

  // Update actual theme when theme changes
  useEffect(() => {
    setActualTheme(theme);
  }, [theme]);

  // Apply theme to document
  useEffect(() => {
    const root = document.documentElement;
    
    // Remove existing theme classes
    root.classList.remove('dark', 'light');
    
    // Add the current theme class
    if (actualTheme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.add('light');
    }
  }, [actualTheme]);

  // Apply density to document
  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('density-compact', 'density-comfortable', 'density-spacious');
    root.classList.add(`density-${density}`);
  }, [density]);

  // Apply animations setting
  useEffect(() => {
    const root = document.documentElement;
    if (!animations) {
      root.classList.add('no-animations');
    } else {
      root.classList.remove('no-animations');
    }
  }, [animations]);

  // Setter functions with localStorage persistence
  const setTheme = (newTheme: 'light' | 'dark') => {
    setThemeState(newTheme);
    saveSetting('theme', newTheme);
  };

  const setDensity = (newDensity: 'compact' | 'comfortable' | 'spacious') => {
    setDensityState(newDensity);
    saveSetting('density', newDensity);
  };

  const setAnimations = (enabled: boolean) => {
    setAnimationsState(enabled);
    saveSetting('animations', enabled);
  };

  const value = {
    theme,
    actualTheme,
    setTheme,
    density,
    setDensity,
    animations,
    setAnimations,
  };

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
};
