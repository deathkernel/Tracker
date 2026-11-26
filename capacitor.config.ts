import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'in.deathkernel.upscprep',
  appName: 'UPSC Prelims Tracker',
  webDir: 'www',
  server: {
    // Keep the web app bundled locally. For the complete tracker experience,
    // run the Python API on the same trusted network and configure its URL
    // with TRACKER_API_URL in a future environment-specific build.
    androidScheme: 'https',
    iosScheme: 'capacitor'
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 0
    }
  }
};

export default config;
