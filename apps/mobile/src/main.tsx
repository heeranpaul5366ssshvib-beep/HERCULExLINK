import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles/globals.css';
import { Capacitor } from '@capacitor/core';
import { SplashScreen } from '@capacitor/splash-screen';
import { StatusBar } from '@capacitor/status-bar';
import { Keyboard } from '@capacitor/keyboard';

async function initCapacitor() {
  if (Capacitor.isNativePlatform()) {
    await SplashScreen.hide();
    await StatusBar.setStyle({ style: 'dark' });
    await StatusBar.setBackgroundColor({ color: '#0d1326' });
    await Keyboard.setStyle({ style: 'dark' });
    Keyboard.addListener('keyboardWillShow', () => {
      document.body.classList.add('keyboard-open');
    });
    Keyboard.addListener('keyboardWillHide', () => {
      document.body.classList.remove('keyboard-open');
    });
  }
}

initCapacitor().then(() => {
  const container = document.getElementById('root');
  if (!container) throw new Error('Root element not found');

  createRoot(container).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
});