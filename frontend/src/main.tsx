import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles.css';
import '@fontsource-variable/inter';
import './platform/modern.css';
import { Toaster } from 'sonner';
import { installResilientFetch } from './platform/connectivity';
import { ErrorBoundary } from './platform/ErrorBoundary';
installResilientFetch();

if ('serviceWorker' in navigator) window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js'));
createRoot(document.getElementById('root')!).render(<React.StrictMode><ErrorBoundary><App/><Toaster position="top-right" richColors closeButton/></ErrorBoundary></React.StrictMode>);

// The static boot screen stays until the session check ends: App (or ErrorBoundary) calls dismissBoot. No timer.
