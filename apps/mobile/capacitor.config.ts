import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.hercule.ai',
  appName: 'HERCULE',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    cleartext: true,
  },
  ios: {
    contentInset: 'automatic',
    scrollEnabled: true,
    limitsNavigationsToAppBoundDomains: true,
    preferredContentMode: 'mobile',
  },
  android: {
    allowMixedContent: true,
    captureInput: true,
    webContentsDebuggingEnabled: false,
    backgroundColor: '#0d1326',
    overrideUserAgent: 'HERCULE/1.0',
    appendUserAgent: 'HERCULE/1.0',
    buildOptions: {
      keystorePath: 'release-key.keystore',
      keystorePassword: process.env.KEYSTORE_PASSWORD,
      keystoreAlias: 'hercule',
      keystoreAliasPassword: process.env.KEYSTORE_ALIAS_PASSWORD,
    },
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      launchAutoHide: true,
      backgroundColor: '#0d1326',
      showSpinner: false,
      androidSplashResourceName: 'splash',
      androidScaleType: 'CENTER_CROP',
    },
    StatusBar: {
      style: 'dark',
      backgroundColor: '#0d1326',
      overlaysWebView: false,
    },
    Keyboard: {
      resize: 'body',
      style: 'dark',
      resizeOnFullScreen: true,
    },
    LocalNotifications: {
      smallIcon: 'ic_stat_hercule',
      iconColor: '#3b82f6',
      sound: 'beep.wav',
    },
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
    Preferences: {
      group: 'hercule-preferences',
    },
  },
};

export default config;